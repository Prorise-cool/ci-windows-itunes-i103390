import os, sys, time, json, traceback, ctypes, subprocess, re
from ctypes import wintypes
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe5_out.log'),'w',encoding='utf-8')
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

def find_exe():
    for c in [r'C:\Program Files\iTunes\iTunes.exe', r'C:\Program Files (x86)\iTunes\iTunes.exe']:
        if os.path.exists(c): return c
    return None

def uia_dump(handle, tag, maxdepth=9, maxlines=2200):
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

def dismiss_popups(tag, maxrounds=8):
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

def itunes_proc_id():
    from pywinauto import Desktop
    d=Desktop(backend='uia')
    for w in d.windows():
        try:
            if (w.window_text() or '')=='iTunes' and w.element_info.class_name=='iTunes':
                return w.element_info.process_id
        except Exception: pass
    return None

def menu_items(pid, tag):
    from pywinauto import Desktop
    d=Desktop(backend='uia'); out=[]
    for w in d.windows():
        try:
            if pid and w.element_info.process_id!=pid: continue
        except Exception: continue
        try: desc=w.descendants()
        except Exception: desc=[]
        for c in desc:
            try: i=c.element_info
            except Exception: continue
            if i.control_type in ('MenuItem','Menu'):
                out.append((w.window_text(),i.control_type,i.name,i.element_info.control_id if hasattr(i,'control_id') else '',c))
    log(tag,'count',len(out), [(x[0][:20],x[1],x[2]) for x in out][:40])
    return out

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    exe=find_exe(); log('EXE',exe)
    if not exe: return
    p=subprocess.Popen([exe]); log('PID',p.pid)
    time.sleep(25); shot('p5_s0_launch')
    for it in range(8):
        ws=win_enum()
        dlg=[w for w in ws if 'license agreement' in (w['title'] or '').lower()]
        if not dlg: log('EULA_GONE_%d'%it); break
        h=dlg[0]['hwnd']; kids=child_enum(h)
        btns=[k for k in kids if normt(k['title']) in ('agree','accept','i agree')]
        if not btns: time.sleep(3); continue
        click_btn(h,btns[0]); shot('p5_eula_%d'%it)
    dismiss_popups('p5',10)
    mw=None
    for att in range(6):
        mw=find_main()
        if mw: break
        dismiss_popups('p5r%d'%att,4); time.sleep(6); shot('p5_retry_%d'%att)
    if not mw: log('NO_MAIN'); shot('p5_nomain'); return
    log('MAIN',json.dumps(mw)); hwnd=mw['hwnd']
    u.SetForegroundWindow(hwnd); time.sleep(2); shot('p5_main')
    uia_dump(hwnd,'p5_main_tree',5,600)
    pid=itunes_proc_id(); log('ITUNES_PID',pid)
    # click Account menu via UIA
    from pywinauto import Desktop
    d=Desktop(backend='uia')
    win=d.window(handle=hwnd)
    acct=None; mb=None
    for c in win.descendants():
        try:
            if c.element_info.control_type=='MenuBar': mb=c
            if c.element_info.control_type=='MenuItem' and (c.element_info.name or '').strip().lower()=='account': acct=c
        except Exception: pass
    log('FOUND_MB_ACCT',bool(mb),bool(acct))
    clicked=False
    if acct is not None:
        try:
            acct.click_input(); clicked=True; log('ACCT_CLICK')
        except Exception as e: log('ACCT_CLICK_ERR',repr(e)[:150])
    time.sleep(2); shot('p5_acct_menu')
    items=menu_items(pid,'MENU_AFTER_ACCT')
    open(os.path.join(OUT,'acct_menu.json'),'w').write(json.dumps([[x[0],x[1],x[2]] for x in items],ensure_ascii=False,indent=1))
    # click Sign In item
    target=None
    for x in items:
        nm=(x[2] or '').lower()
        if 'sign in' in nm or 'sign  in' in nm: target=x; break
    if target is None:
        for x in items:
            nm=(x[2] or '').lower()
            if 'sign' in nm: target=x; break
    log('TARGET_SIGNIN',(target[2] if target else None))
    if target is not None:
        try: target[4].click_input(); log('SIGNIN_CLICKED')
        except Exception as e: log('SIGNIN_CLICK_ERR',repr(e)[:150])
    seen=set(w['hwnd'] for w in win_enum())
    for t in range(8):
        time.sleep(5); shot('p5_signin_%d'%t)
        ws=win_enum()
        log('WS_%d'%t, json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2000])
        new=[w for w in ws if w['hwnd'] not in seen]
        for w in new:
            seen.add(w['hwnd'])
            kids=child_enum(w['hwnd'])
            log('NEWKIDS_%d'%t, w['title'], w['class'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:4000])
            uia_dump(w['hwnd'],'p5_new_%d_%s'%(t,re.sub(r'\W+','_',(w['title'] or w['class'] or 'x')[:20])),9,2200)
        # dump menus too (sheet may present items)
        menu_items(pid,'MENU_T%d'%t)
        if new: break
    uia_dump(hwnd,'p5_maintree_after',9,2600)
    # look for create text in UIA of all itunes windows
    create_hits=[]
    for w in d.windows():
        try:
            if pid and w.element_info.process_id!=pid: continue
            for c in w.descendants():
                try: nm=(c.element_info.name or '')
                except Exception: continue
                if re.search(r'create',nm,re.I) and re.search(r'apple|id|account',nm,re.I):
                    create_hits.append((w.window_text()[:30],nm[:120],c))
        except Exception: pass
    log('CREATE_HITS',[(h[0],h[1]) for h in create_hits][:10])
    if create_hits:
        try: create_hits[0][2].click_input(); log('CREATE_CLICKED',create_hits[0][1][:80])
        except Exception as e: log('CREATE_CLICK_ERR',repr(e)[:150])
        seen2=set(w['hwnd'] for w in win_enum())
        for t in range(6):
            time.sleep(7); shot('p5_create_%d'%t)
            ws=win_enum()
            log('CWS_%d'%t, json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2000])
            for w in ws:
                if w['hwnd'] in seen2: continue
                seen2.add(w['hwnd'])
                kids=child_enum(w['hwnd'])
                log('CNEWKIDS_%d'%t, w['title'], w['class'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:4000])
                uia_dump(w['hwnd'],'p5_cnew_%d_%s'%(t,re.sub(r'\W+','_',(w['title'] or w['class'] or 'x')[:20])),9,2400)
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))

if __name__=='__main__':
    try: main()
    except Exception: log('FATAL',traceback.format_exc())
