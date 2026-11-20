import os, sys, time, json, traceback, ctypes, subprocess, re
from ctypes import wintypes
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe6_out.log'),'w',encoding='utf-8')
u=ctypes.windll.user32
def log(*a):
    s=' '.join(str(x) for x in a); print(s); LOG.write(s+'\n'); LOG.flush()
def shot(name):
    try:
        from PIL import ImageGrab
        im=ImageGrab.grab(all_screens=True); p=os.path.join(OUT,name+'.png'); im.save(p); log('SHOT',name,im.size); return p
    except Exception as e: log('SHOT_ERR',name,repr(e)); return None

def win_enum():
    res=[]
    CB=ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h,l):
        try:
            if u.IsWindowVisible(h):
                b=ctypes.create_unicode_buffer(600); u.GetWindowTextW(h,b,600)
                c=ctypes.create_unicode_buffer(256); u.GetClassNameW(h,c,256)
                r=wintypes.RECT(); u.GetWindowRect(h,ctypes.byref(r))
                pid=wintypes.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
                res.append({'hwnd':int(h),'title':b.value,'class':c.value,'rect':(r.left,r.top,r.right,r.bottom),'menu':bool(u.GetMenu(int(h))),'pid':int(pid.value)})
        except Exception: pass
        return True
    u.EnumWindows(CB(cb),0); return res

def child_enum(hp):
    res=[]
    CB=ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h,l):
        try:
            b=ctypes.create_unicode_buffer(600); u.GetWindowTextW(h,b,600)
            c=ctypes.create_unicode_buffer(256); u.GetClassNameW(h,c,256)
            r=wintypes.RECT(); u.GetWindowRect(h,ctypes.byref(r))
            res.append({'hwnd':int(h),'title':b.value,'class':c.value,'id':int(u.GetDlgCtrlID(h)),'rect':(r.left,r.top,r.right,r.bottom),'visible':bool(u.IsWindowVisible(h))})
        except Exception: pass
        return True
    u.EnumChildWindows(hp,CB(cb),0); return res

def normt(t): return (t or '').replace('&','').replace('\t',' ').strip().lower()
def click_rect(cx,cy):
    u.SetCursorPos(int(cx),int(cy)); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0); log('MOUSE',cx,cy)
def send_cmd(hwnd,cid):
    log('WM_COMMAND',hex(int(hwnd)),cid); u.PostMessageW(int(hwnd),0x111,cid,0)
def click_btn(h,b):
    r=b['rect']; u.SetForegroundWindow(h); time.sleep(0.5)
    if r[2]>r[0] and r[3]>r[1]:
        click_rect((r[0]+r[2])//2,(r[1]+r[3])//2); time.sleep(2.5)
    if any(w['hwnd']==h for w in win_enum()) and b['id']>0:
        send_cmd(h,b['id']); time.sleep(2.5)

def find_exe():
    for c in [r'C:\Program Files\iTunes\iTunes.exe', r'C:\Program Files (x86)\iTunes\iTunes.exe']:
        if os.path.exists(c): return c
    return None

def uia_dump(handle, tag, maxdepth=9, maxlines=2200):
    from pywinauto import Desktop
    try: w=Desktop(backend='uia').window(handle=handle)
    except Exception as e: log('UIA_BIND_ERR',tag,repr(e)[:120]); return []
    lines=[]
    def rec(c,d):
        if len(lines)>=maxlines: return
        try:
            i=c.element_info
            lines.append('%s[%s] class=%r name=%r aid=%r'%('  '*d,i.control_type,i.class_name,(i.name or '')[:200],i.automation_id))
        except Exception: return
        if d<maxdepth:
            try: ch=c.children()
            except Exception: ch=[]
            for x in ch: rec(x,d+1)
    rec(w,0)
    open(os.path.join(OUT,tag+'.txt'),'w',encoding='utf-8').write('\n'.join(lines)); log('UIA_DUMP',tag,len(lines))
    return lines

def dismiss_popups(tag, maxrounds=10):
    for i in range(maxrounds):
        ws=win_enum()
        dl=[w for w in ws if w['class']=='iTunesCustomModalDialog' and 'license agreement' not in (w['title'] or '').lower()]
        if not dl: return
        h=dl[0]['hwnd']; kids=child_enum(h)
        log(tag+'_DLG%d'%i, json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:1400])
        btns=[k for k in kids if normt(k['title']) in ('ok','continue','close','next','get started','agree','done','yes','no thanks','don\'t send','later','skip')]
        if not btns: shot(tag+'_nobtn_%d'%i); return
        click_btn(h,btns[0]); shot('%s_popup_%d'%(tag,i))

def find_main():
    ws=win_enum()
    cand=[w for w in ws if w['class']=='iTunes' and 'license' not in (w['title'] or '').lower()]
    if cand: return max(cand,key=lambda w:(w['rect'][2]-w['rect'][0])*(w['rect'][3]-w['rect'][1]))
    return None

u.GetMenu.restype=ctypes.c_void_p; u.GetMenu.argtypes=[wintypes.HWND]
u.GetSubMenu.restype=ctypes.c_void_p; u.GetSubMenu.argtypes=[ctypes.c_void_p,ctypes.c_int]
u.GetMenuItemCount.restype=ctypes.c_int; u.GetMenuItemCount.argtypes=[ctypes.c_void_p]
u.GetMenuItemID.restype=ctypes.c_int; u.GetMenuItemID.argtypes=[ctypes.c_void_p,ctypes.c_uint]
u.GetMenuStringW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_wchar_p,ctypes.c_int,ctypes.c_uint]
def enum_menus(hwnd):
    """Enumerate native Win32 menu bar; return {top_name:[(pos,id,text)]} and flat list."""
    out={}; flat=[]
    hm=u.GetMenu(wintypes.HWND(int(hwnd)))
    if not hm: log('GETMENU_NULL'); return out,flat
    n=u.GetMenuItemCount(hm)
    log('MENU_TOP_COUNT',n)
    for i in range(n):
        buf=ctypes.create_unicode_buffer(512)
        u.GetMenuStringW(hm,i,buf,512,0x400)
        top=buf.value
        hsub=u.GetSubMenu(hm,i)
        items=[]
        if hsub:
            cn=u.GetMenuItemCount(hsub)
            for j in range(cn):
                b2=ctypes.create_unicode_buffer(512)
                u.GetMenuStringW(hsub,j,b2,512,0x400)
                mid=u.GetMenuItemID(hsub,j)
                txt=b2.value.replace('&','').replace('\t',' ')
                items.append((j,int(mid),txt))
                flat.append((top,j,int(mid),txt))
        out[top]=items
        log('MENU_TOP',repr(top),json.dumps(items,ensure_ascii=False)[:2000])
    return out,flat

def texts_of_window(h):
    names=[]
    try: names.append(('WND', h, win_title(h)))
    except Exception: pass
    for k in child_enum(h):
        if k['title']: names.append((k['class'],k['id'],k['title']))
    log('TEXTS',hex(h),json.dumps(names,ensure_ascii=False)[:3000])
    return names

def win_title(h):
    b=ctypes.create_unicode_buffer(600); u.GetWindowTextW(int(h),b,600); return b.value

def collect_new(seen, tag, rounds=12, wait=5):
    got=[]
    for t in range(rounds):
        time.sleep(wait); shot('%s_%d'%(tag,t))
        ws=win_enum()
        try: log(tag+'_WS%d'%t, json.dumps([(w['title'],w['class'],w['rect'],w['pid']) for w in ws],ensure_ascii=False)[:2500])
        except Exception: pass
        new=[w for w in ws if w['hwnd'] not in seen]
        for w in new:
            seen.add(w['hwnd']); got.append(w)
            log(tag+'_NEW',w['title'],w['class'],w['rect'])
            try: texts_of_window(w['hwnd'])
            except Exception as e: log('TEXTERR',repr(e)[:120])
            uia_dump(w['hwnd'],'%s_new_%d_%s'%(tag,t,re.sub(r'\W+','_',(w['title'] or w['class'] or 'x')[:24])),9,2600)
        if new: break
    return got

def uia_find_all(pid, name_re):
    """Return list of (window_title, control_type, name, control)."""
    from pywinauto import Desktop
    d=Desktop(backend='uia'); hits=[]
    for w in d.windows():
        try:
            if pid and w.element_info.process_id!=pid: continue
        except Exception: continue
        try: desc=w.descendants()
        except Exception: desc=[]
        for c in desc:
            try: nm=c.element_info.name or ''
            except Exception: continue
            if name_re.search(nm): hits.append((win_title(w.handle), c.element_info.control_type, nm, c))
    return hits

def find_child_by_text(pid, pattern, visible_only=True):
    hits=[]
    for w in win_enum():
        if w['pid']!=pid: continue
        for k in child_enum(w['hwnd']):
            if visible_only and not k['visible']: continue
            if k['title'] and pattern.search(k['title']):
                hits.append((w,k))
    return hits

def snapshot_state(pid, tag):
    ws=[w for w in win_enum() if w['pid']==pid]
    log(tag+'_WINS', json.dumps([(w['title'],w['class'],w['rect'],w['hwnd']) for w in ws],ensure_ascii=False)[:3000])
    seen=set()
    for w in ws:
        for k in child_enum(w['hwnd']):
            if k['title'] and k['title'] not in seen:
                seen.add(k['title'])
                log(tag+'_KID', w['class'], w['hwnd'], k['class'], k['id'], repr(k['title'])[:200])
    return ws

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    exe=find_exe(); log('EXE',exe)
    if not exe: return
    p=subprocess.Popen([exe]); log('PID',p.pid)
    time.sleep(25); shot('p7_s0_launch')
    for it in range(8):
        ws=win_enum()
        dlg=[w for w in ws if 'license agreement' in (w['title'] or '').lower()]
        if not dlg: log('EULA_GONE_%d'%it); break
        h=dlg[0]['hwnd']; kids=child_enum(h)
        btns=[k for k in kids if normt(k['title']) in ('agree','accept','i agree')]
        if not btns: time.sleep(3); continue
        click_btn(h,btns[0]); shot('p7_eula_%d'%it)
    dismiss_popups('p7',10)
    mw=None
    for att in range(6):
        mw=find_main()
        if mw: break
        dismiss_popups('p7r%d'%att,4); time.sleep(6); shot('p7_retry_%d'%att)
    if not mw: log('NO_MAIN'); shot('p7_nomain'); return
    log('MAIN',json.dumps(mw)); hwnd=mw['hwnd']
    u.SetForegroundWindow(hwnd); time.sleep(2); shot('p7_main')
    pid=p.pid
    # open Account menu via UIA then Sign In
    from pywinauto import Desktop
    d=Desktop(backend='uia'); acct=None
    for c in d.window(handle=hwnd).descendants():
        try:
            if c.element_info.control_type=='MenuItem' and (c.element_info.name or '').strip().lower()=='account': acct=c; break
        except Exception: pass
    if acct is not None:
        try: acct.click_input(); log('ACCT_CLICK'); time.sleep(2)
        except Exception as e: log('ACCT_CLICK_ERR',repr(e)[:150])
    hits=uia_find_all(pid, re.compile(r'sign\s*in',re.I))
    log('UIA_SIGNIN_HITS',[(h[1],h[2]) for h in hits][:10])
    if hits:
        try: hits[0][3].click_input(); log('SIGNIN_CLICKED')
        except Exception as e: log('SIGNIN_CLICK_ERR',repr(e)[:150])
    # wait for Create &New Apple Account button
    create_btn=None
    for t in range(10):
        time.sleep(4); shot('p7_signin_%d'%t)
        h2=find_child_by_text(pid, re.compile(r'create\s*&?\s*new\s*apple',re.I))
        log('CREATE_BTN_TRY%d'%t, [(w['class'],k['class'],k['id'],k['title'],k['rect']) for w,k in h2][:5])
        if h2: create_btn=h2[0]; break
    snapshot_state(pid,'p7_signin_state')
    if create_btn is None:
        log('NO_CREATE_BTN'); shot('p7_nocreatebtn'); uia_dump(hwnd,'p7_tree_nocreate',10,3000); return
    w,k=create_btn
    log('CREATE_BTN_FOUND',w['class'],w['hwnd'],k['class'],k['id'],k['title'],k['rect'])
    # click it
    r=k['rect']; u.SetForegroundWindow(w['hwnd']); time.sleep(0.5)
    click_rect((r[0]+r[2])//2,(r[1]+r[3])//2)
    t0=time.time(); prev_sig=None
    for t in range(20):
        time.sleep(6); shot('p7_create_%d'%t)
        ws=snapshot_state(pid,'p7_c%d'%t)
        uia_dump(hwnd,'p7_tree_c%d'%t,10,3000)
        # each pid window UIA
        for ww in ws:
            cls=(ww['class'] or '').lower()
            if any(x in cls for x in ('chrome','edge','webview','cef','internet explorer','msedge')) or ww['class']!='iTunes':
                uia_dump(ww['hwnd'],'p7_w_%d_%s'%(t,re.sub(r'\W+','_',(ww['title'] or ww['class'] or 'x')[:20])),10,3000)
        if time.time()-t0>150: break
    # final analyses
    pat=re.compile(r'virtual\s*machine|not\s+supported|cannot\s+be\s+created|not\s+available|captcha|verification|image\s+code|code|birth|country|first\s+name|last\s+name|password|email',re.I)
    for t in range(1):
        pass
    hits=uia_find_all(pid, pat)
    log('FINAL_TEXT_HITS', [(h[0][:25],h[1],h[2][:120]) for h in hits][:80])
    # edit fields
    edits=[]
    for w in win_enum():
        if w['pid']!=pid: continue
        for k in child_enum(w['hwnd']):
            if k['class'].lower() in ('edit','richedit20w','richedit50w') or 'edit' in k['class'].lower():
                edits.append((w['class'],w['hwnd'],k['class'],k['id'],k['rect'],k['title']))
    log('EDIT_FIELDS',json.dumps(edits,ensure_ascii=False)[:4000])
    shot('p7_end')
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))

if __name__=='__main__':
    try: main()
    except Exception: log('FATAL',traceback.format_exc())
