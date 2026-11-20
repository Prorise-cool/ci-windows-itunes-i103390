import os, sys, time, json, traceback, ctypes, subprocess, urllib.request, re
from ctypes import wintypes
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe4_out.log'),'w',encoding='utf-8')
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
                res.append({'hwnd':int(h),'title':b.value,'class':c.value,'rect':(r.left,r.top,r.right,r.bottom),'menu':bool(u.GetMenu(int(h)))})
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

def dump_menu(hwnd):
    hm=u.GetMenu(int(hwnd)); out=[]
    if not hm: return out
    n=u.GetMenuItemCount(hm)
    for i in range(n):
        b=ctypes.create_unicode_buffer(512); u.GetMenuStringW(hm,i,b,512,0x400)
        e={'text':b.value,'id':int(u.GetMenuItemID(hm,i)),'items':[]}
        sub=u.GetSubMenu(hm,i)
        if sub:
            for j in range(u.GetMenuItemCount(sub)):
                b2=ctypes.create_unicode_buffer(512); u.GetMenuStringW(sub,j,b2,512,0x400)
                st=int(u.GetMenuState(sub,j,0))
                e['items'].append({'text':b2.value,'id':int(u.GetMenuItemID(sub,j)),'state':st})
        out.append(e)
    return out

def uia_dump(handle, tag, maxdepth=8, maxlines=1800):
    from pywinauto import Desktop
    try: w=Desktop(backend='uia').window(handle=handle)
    except Exception as e: log('UIA_BIND_ERR',tag,repr(e)[:120]); return
    lines=[]
    def rec(c,d):
        if len(lines)>=maxlines: return
        try:
            i=c.element_info
            lines.append('%s[%s] class=%r name=%r aid=%r'%('  '*d,i.control_type,i.class_name,(i.name or '')[:160],i.automation_id))
        except Exception: return
        if d<maxdepth:
            try: ch=c.children()
            except Exception: ch=[]
            for x in ch: rec(x,d+1)
    rec(w,0)
    open(os.path.join(OUT,tag+'.txt'),'w',encoding='utf-8').write('\n'.join(lines)); log('UIA_DUMP',tag,len(lines))

def find_exe():
    for c in [r'C:\Program Files\iTunes\iTunes.exe', r'C:\Program Files (x86)\iTunes\iTunes.exe']:
        if os.path.exists(c): return c
    return None

def dismiss_popups(tag, maxrounds=8):
    for i in range(maxrounds):
        ws=win_enum()
        dl=[w for w in ws if w['class']=='iTunesCustomModalDialog' and 'license agreement' not in (w['title'] or '').lower()]
        if not dl: return
        h=dl[0]['hwnd']; kids=child_enum(h)
        log(tag+'_DLG%d'%i, json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:1400])
        btns=[k for k in kids if normt(k['title']) in ('ok','continue','close','next','get started','agree','done','yes','no thanks','don\'t send','later','skip')]
        log(tag+'_BTN',[(k['title'],k['id']) for k in btns])
        if not btns:
            shot(tag+'_nobtn_%d'%i); return
        click_btn(h,btns[0]); shot('%s_popup_%d'%(tag,i))

def find_main():
    ws=win_enum()
    log('WIN_MENU', json.dumps([(w['title'],w['class'],w['rect'],w['menu']) for w in ws],ensure_ascii=False)[:2500])
    cand=[w for w in ws if w['menu'] and 'license' not in (w['title'] or '').lower()]
    if cand: return max(cand,key=lambda w:(w['rect'][2]-w['rect'][0])*(w['rect'][3]-w['rect'][1]))
    return None

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    exe=find_exe(); log('EXE',exe)
    if not exe: return
    p=subprocess.Popen([exe]); log('PID',p.pid)
    time.sleep(25); shot('p4_s0_launch')
    # EULA
    for it in range(8):
        ws=win_enum()
        dlg=[w for w in ws if 'license agreement' in (w['title'] or '').lower()]
        if not dlg: log('EULA_GONE_%d'%it); break
        h=dlg[0]['hwnd']; kids=child_enum(h)
        log('EULA_KIDS_%d'%it, json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:1200])
        btns=[k for k in kids if normt(k['title']) in ('agree','accept','i agree')]
        if not btns: log('NO_AGREE'); time.sleep(3); continue
        click_btn(h,btns[0]); shot('p4_eula_%d'%it)
    # other popups (audio config etc.)
    dismiss_popups('p4',10)
    mw=None
    for att in range(6):
        mw=find_main()
        if mw: break
        log('MAIN_RETRY_%d'%att); dismiss_popups('p4r%d'%att,4); time.sleep(6); shot('p4_retry_%d'%att)
    if not mw: log('NO_MAIN'); shot('p4_nomain'); return
    log('MAIN',json.dumps(mw))
    hwnd=mw['hwnd']
    menu=dump_menu(hwnd)
    open(os.path.join(OUT,'menu4.json'),'w').write(json.dumps(menu,ensure_ascii=False,indent=1))
    log('MENU', json.dumps(menu,ensure_ascii=False)[:3500])
    u.SetForegroundWindow(hwnd); time.sleep(1); shot('p4_main'); uia_dump(hwnd,'p4_main_tree',8,1800)
    cid=None
    for m in menu:
        mt=(m['text'] or '').replace('&','').lower()
        for it in m['items']:
            if 'sign in' in (it['text'] or '').lower().replace('&',''):
                cid=it['id']; log('SIGNIN_ITEM',m['text'],it)
    if cid is None:
        for m in menu:
            for it in m['items']:
                if 'sign' in (it['text'] or '').lower(): cid=it['id']; log('SIGNIN_ANY',m['text'],it)
    if cid is None: log('NO_SIGNIN_ITEM')
    else: send_cmd(hwnd,cid)
    # watch for sign-in UI (webview page or dialog)
    seen=set(w['hwnd'] for w in win_enum())
    for t in range(6):
        time.sleep(6); shot('p4_aftersignin_%d'%t)
        ws=win_enum()
        new=[w for w in ws if w['hwnd'] not in seen]
        log('SIGNIN_WIN_%d'%t, json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2200])
        for w in new:
            kids=child_enum(w['hwnd'])
            log('SIGNIN_KIDS_%d'%t, w['title'], w['class'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:3500])
            uia_dump(w['hwnd'],'p4_signin_%d_%s'%(t,re.sub(r'\W+','_',(w['title'] or w['class'] or 'x')[:20])),8,1800)
            seen.add(w['hwnd'])
        if any('sign' in (w['title'] or '').lower() or 'apple' in (w['title'] or '').lower() for w in new): break
    # also dump main window uia again + find create
    uia_dump(hwnd,'p4_maintree_after',8,2000)
    cand=[]
    for w in win_enum():
        for k in child_enum(w['hwnd']):
            t=(k['title'] or '').strip()
            tl=t.lower()
            if t and 'create' in tl and 'paging' not in tl and 'virtual memory' not in tl:
                cand.append((w,k))
    log('CREATE_NATIVE', json.dumps([(w['title'],k['title'],k['class'],k['id'],k['rect']) for w,k in cand],ensure_ascii=False)[:1500])
    clicked=False
    if cand:
        w,k=cand[0]; click_btn(w['hwnd'],k); clicked=True
    if not clicked:
        try:
            from pywinauto import Desktop
            d=Desktop(backend='uia')
            for w in d.windows():
                try: n=(w.window_text() or '')
                except Exception: continue
                if 'itunes' not in n.lower() and 'apple' not in n.lower(): continue
                for c in w.descendants():
                    try: nm=(c.element_info.name or '').lower()
                    except Exception: continue
                    if 'create' in nm and ('apple' in nm or 'account' in nm or 'id' in nm):
                        log('UIA_CREATE',n,nm); c.click_input(); clicked=True; break
                if clicked: break
        except Exception as e: log('UIA_CREATE_ERR',repr(e)[:150])
    log('CLICKED_CREATE',clicked)
    seen2=set(w['hwnd'] for w in win_enum())
    for t in range(5):
        time.sleep(8); shot('p4_aftercreate_%d'%t)
        ws=win_enum()
        log('CREATE_WIN_%d'%t, json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2200])
        for w in ws:
            if w['hwnd'] in seen2: continue
            seen2.add(w['hwnd'])
            kids=child_enum(w['hwnd'])
            log('CREATE_KIDS_%d'%t, w['title'], w['class'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:4000])
            uia_dump(w['hwnd'],'p4_create_%d_%s'%(t,re.sub(r'\W+','_',(w['title'] or w['class'] or 'x')[:20])),9,2200)
    uia_dump(hwnd,'p4_maintree_end',8,2000)
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))

if __name__=='__main__':
    try: main()
    except Exception: log('FATAL',traceback.format_exc())
