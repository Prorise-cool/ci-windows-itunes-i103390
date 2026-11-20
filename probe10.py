import os, sys, time, json, traceback, ctypes, subprocess, re
from ctypes import wintypes
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe10_out.log'),'w',encoding='utf-8')
u=ctypes.windll.user32; k=ctypes.windll.kernel32
def log(*a):
    s=' '.join(str(x) for x in a); print(s); LOG.write(s+'\n'); LOG.flush()
def shot(name):
    try:
        from PIL import ImageGrab
        im=ImageGrab.grab(all_screens=True); p=os.path.join(OUT,name+'.png'); im.save(p); log('SHOT',name,im.size); return p
    except Exception as e: log('SHOT_ERR',name,repr(e)); return None
def _enum(vis_only):
    res=[]
    CB=ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h,l):
        try:
            vis=bool(u.IsWindowVisible(h))
            if vis_only and not vis: return True
            b=ctypes.create_unicode_buffer(600); u.GetWindowTextW(h,b,600)
            c=ctypes.create_unicode_buffer(256); u.GetClassNameW(h,c,256)
            r=wintypes.RECT(); u.GetWindowRect(h,ctypes.byref(r))
            pid=wintypes.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(pid))
            res.append({'hwnd':int(h),'title':b.value,'class':c.value,'rect':(r.left,r.top,r.right,r.bottom),'visible':vis,'pid':int(pid.value)})
        except Exception: pass
        return True
    u.EnumWindows(CB(cb),0); return res
def win_enum(): return _enum(True)
def all_win_enum(): return _enum(False)
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
def click_btn(h,b):
    r=b['rect']; u.SetForegroundWindow(h); time.sleep(0.5)
    if r[2]>r[0] and r[3]>r[1]: click_rect((r[0]+r[2])//2,(r[1]+r[3])//2); time.sleep(1.5)
def find_exe():
    for c in [r'C:\Program Files\iTunes\iTunes.exe', r'C:\Program Files (x86)\iTunes\iTunes.exe']:
        if os.path.exists(c): return c
    return None
def win_title(h):
    b=ctypes.create_unicode_buffer(600); u.GetWindowTextW(int(h),b,600); return b.value
def find_main():
    cand=[w for w in win_enum() if w['class']=='iTunes' and 'license' not in (w['title'] or '').lower()]
    if cand: return max(cand,key=lambda w:(w['rect'][2]-w['rect'][0])*(w['rect'][3]-w['rect'][1]))
    return None
def dismiss_popups(tag, maxrounds=8):
    for i in range(maxrounds):
        ws=win_enum()
        dl=[w for w in ws if w['class']=='iTunesCustomModalDialog' and 'license agreement' not in (w['title'] or '').lower()]
        if not dl: return
        h=dl[0]['hwnd']; kids=child_enum(h)
        log(tag+'_DLG%d'%i, json.dumps([(x['class'],x['title'],x['id'],x['visible']) for x in kids],ensure_ascii=False)[:1200])
        btns=[x for x in kids if normt(x['title']) in ('ok','continue','close','next','get started','agree','done','yes','no thanks','don\'t send','later','skip')]
        if not btns: shot(tag+'_nobtn_%d'%i); return
        click_btn(h,btns[0]); shot('%s_popup_%d'%(tag,i))
def uia_desc(handle):
    from pywinauto import Desktop
    try: return Desktop(backend='uia').window(handle=handle).descendants()
    except Exception as e: log('UIA_ERR',repr(e)[:100]); return []
def dump_tree(handle,tag,maxdepth=8,maxlines=2500):
    from pywinauto import Desktop
    try: w=Desktop(backend='uia').window(handle=handle)
    except Exception as e: log('UIA_BIND_ERR',tag,repr(e)[:100]); return 0
    lines=[]
    def rec(c,d):
        if len(lines)>=maxlines: return
        try:
            i=c.element_info
            lines.append('%s[%s] class=%r name=%r aid=%r'%('  '*d,i.control_type,i.class_name,(i.name or '')[:220],i.automation_id))
        except Exception: return
        if d<maxdepth:
            try: ch=c.children()
            except Exception: ch=[]
            for x in ch: rec(x,d+1)
    rec(w,0)
    open(os.path.join(OUT,tag+'.txt'),'w',encoding='utf-8').write('\n'.join(lines))
    log('TREE',tag,len(lines)); return len(lines)
def tasklist():
    try:
        o=subprocess.check_output('tasklist /FO CSV /NH',shell=True,text=True,errors='replace')
        return set(l.split('","')[0].strip('"').lower()+'|'+l.split('","')[1].strip('"') for l in o.splitlines() if '","' in l)
    except Exception: return set()
def dump_all_windows(pid,tag):
    ws=[w for w in all_win_enum() if w['pid']==pid]
    log(tag+'_ALLWINS', json.dumps([(w['title'],w['class'],w['rect'],w['visible'],w['hwnd']) for w in ws],ensure_ascii=False)[:4000])
    return ws
def find_signin_dialog(pid):
    for w in all_win_enum():
        if w['pid']!=pid: continue
        ck=child_enum(w['hwnd'])
        t=' | '.join(x['title'] for x in ck if x['title'])
        if 'apple account' in t.lower() and 'create' in t.lower(): return w,ck
    return None,[]
def uia_click_name(pid, pat, action='invoke'):
    from pywinauto import Desktop
    d=Desktop(backend='uia')
    for w in d.windows():
        try:
            if w.element_info.process_id!=pid: continue
        except Exception: continue
        try: desc=w.descendants()
        except Exception: continue
        for c in desc:
            try: nm=c.element_info.name or ''
            except Exception: continue
            if pat.search(nm):
                try:
                    if action=='invoke': c.invoke()
                    else: c.click_input()
                    log('UIA_ACT',action,repr(nm)[:120]); return True
                except Exception as e: log('UIA_ACT_ERR',action,repr(nm)[:80],repr(e)[:100])
    return False
def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    exe=find_exe(); log('EXE',exe)
    if not exe: return
    p=subprocess.Popen([exe]); log('PID',p.pid); pid=p.pid
    time.sleep(22); shot('p10_launch')
    for it in range(8):
        ws=win_enum(); dlg=[w for w in ws if 'license agreement' in (w['title'] or '').lower()]
        if not dlg: log('EULA_GONE_%d'%it); break
        h=dlg[0]['hwnd']; kids=child_enum(h)
        btns=[x for x in kids if normt(x['title']) in ('agree','accept','i agree')]
        if not btns: time.sleep(3); continue
        click_btn(h,btns[0]); shot('p10_eula_%d'%it)
    dismiss_popups('p10',8)
    mw=None
    for att in range(6):
        mw=find_main()
        if mw: break
        dismiss_popups('p10r%d'%att,3); time.sleep(5); shot('p10_retry_%d'%att)
    if not mw: log('NO_MAIN'); shot('p10_nomain'); return
    hwnd=mw['hwnd']; log('MAIN',json.dumps(mw))
    u.SetForegroundWindow(hwnd); time.sleep(1); shot('p10_main')
    # 1) dismiss the first-run library-sharing modal (No Thanks) if present
    seen=set()
    for w in all_win_enum():
        if w['pid']!=pid: continue
        for x in child_enum(w['hwnd']):
            if x['title'] and x['title'].lower() in ('no thanks','agree','not now') and x['title'] not in seen:
                seen.add(x['title']); log('WELCOME_BTN',w['class'],w['hwnd'],x['class'],x['id'],repr(x['title']),x['visible'])
    if uia_click_name(pid, re.compile(r'^\s*No Thanks\s*$',re.I),'invoke'):
        time.sleep(2); log('WELCOME_DISMISSED'); shot('p10_welcome_gone')
    else:
        log('WELCOME_NOT_FOUND')
    # 2) Account menu: enumerate UIA MenuItems (do not click unknown items yet)
    from pywinauto import Desktop
    d=Desktop(backend='uia')
    acct=None
    try:
        for c in d.window(handle=hwnd).descendants():
            try:
                if c.element_info.control_type=='MenuItem' and (c.element_info.name or '').strip().lower().startswith('account'):
                    acct=c; break
            except Exception: pass
    except Exception as e: log('ACCT_FIND_ERR',repr(e)[:100])
    if acct is not None:
        try:
            acct.click_input(); time.sleep(2); shot('p10_acct_menu'); log('ACCT_MENU_OPEN')
            items=[]
            for w in d.windows():
                try:
                    if w.element_info.process_id!=pid: continue
                    for c in w.descendants():
                        try:
                            if c.element_info.control_type=='MenuItem': items.append(c.element_info.name)
                        except Exception: pass
                except Exception: pass
            log('ACCT_MENU_ITEMS', json.dumps(items,ensure_ascii=False)[:2500])
            # dump menu window trees
            for w in win_enum():
                if w['pid']==pid and w['class']!='iTunes': dump_tree(w['hwnd'],'p10_menuw_'+re.sub(r'\W+','_',w['class'])[:20],6,400)
            hit=[i for i in items if i and 'create' in i.lower()]
            if hit:
                log('ACCT_CREATE_MENU_HIT',hit[:3])
                uia_click_name(pid, re.compile(re.escape(hit[0]),re.I),'invoke'); time.sleep(4); shot('p10_acct_create_invoked')
            u.keybd_event(0x1B,0,0,0); u.keybd_event(0x1B,0,2,0); time.sleep(1)
        except Exception as e: log('ACCT_ERR',repr(e)[:120])
    # 3) open sign-in dialog
    if uia_click_name(pid, re.compile(r'sign\s*in',re.I),'click'):
        log('SIGNIN_CLICKED')
    time.sleep(5); shot('p10_signin')
    dlg,kids=find_signin_dialog(pid)
    if not dlg: time.sleep(5); dlg,kids=find_signin_dialog(pid)
    log('SIGNIN_DLG',json.dumps(dlg,ensure_ascii=False) if dlg else None)
    log('SIGNIN_KIDS',json.dumps([(x['class'],x['id'],x['title'],x['rect'],x['visible']) for x in kids],ensure_ascii=False)[:2500])
    if not dlg: dump_all_windows(pid,'p10_nodlg'); shot('p10_nodlg'); log('DONE_NODLG',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())); return
    btn=[x for x in kids if 'create' in (x['title'] or '').lower() and 'apple' in (x['title'] or '').lower()]
    if not btn: log('NO_CREATE_BTN'); dump_all_windows(pid,'p10_nobtn'); return
    b=btn[0]; r=b['rect']; dh=dlg['hwnd']
    u.GetDlgItem.restype=ctypes.c_void_p; u.GetDlgItem.argtypes=[ctypes.c_void_p,ctypes.c_int]
    u.SendMessageW.restype=ctypes.c_void_p; u.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_void_p]
    u.ShowWindow.argtypes=[ctypes.c_void_p,ctypes.c_int]
    hbtn=u.GetDlgItem(wintypes.HWND(int(dh)),int(b['id']))
    log('GETDLGITEM',hex(int(hbtn)) if hbtn else None)
    tl0=tasklist()
    if hbtn:
        u.ShowWindow(hbtn,5); time.sleep(1)
        log('VISIBLE_AFTER_SHOW',bool(u.IsWindowVisible(hbtn)))
        shot('p10_btn_shown')
        # Attempt A: BM_SETSTATE(1) then BM_CLICK
        log('BM_SETSTATE_RET',u.SendMessageW(hbtn,0x00F3,1,None)); time.sleep(0.4)
        log('BM_CLICK_RET',u.SendMessageW(hbtn,0x00F5,None,None)); time.sleep(5)
        shot('p10_A_after_bmclick')
        dump_all_windows(pid,'p10_A')
        # Attempt B: foreground + focus + one Tab + one Enter
        dlg2,_=find_signin_dialog(pid)
        if dlg2:
            u.SetForegroundWindow(wintypes.HWND(int(dlg2['hwnd']))); time.sleep(0.5)
            hb2=u.GetDlgItem(wintypes.HWND(int(dlg2['hwnd'])),int(b['id']))
            if hb2:
                cur=k.GetCurrentThreadId(); tp=wintypes.DWORD(); u.GetWindowThreadProcessId(wintypes.HWND(int(dlg2['hwnd'])),ctypes.byref(tp))
                try: u.AttachThreadInput(cur,tp.value,True)
                except Exception as e: log('ATTACH_ERR',repr(e)[:80])
                try: u.SetFocus(hb2); log('SETFOCUS_OK',hex(int(hb2)))
                except Exception as e: log('SETFOCUS_ERR',repr(e)[:80])
                try: u.AttachThreadInput(cur,tp.value,False)
                except Exception: pass
            time.sleep(0.4)
            log('KEY_TAB'); u.keybd_event(0x09,0,0,0); u.keybd_event(0x09,0,2,0); time.sleep(0.4)
            log('KEY_ENTER'); u.keybd_event(0x0D,0,0,0); u.keybd_event(0x0D,0,2,0); time.sleep(5)
            shot('p10_B_after_keys')
            dump_all_windows(pid,'p10_B')
        # Attempt C: UIA invoke on the (now visible) create button, once
        dlg3,_=find_signin_dialog(pid)
        if dlg3:
            try:
                els=[c for c in d.window(handle=dlg3['hwnd']).descendants()]
            except Exception as e: els=[]; log('UIA_DLG_ERR',repr(e)[:100])
            got=False
            for c in els:
                try:
                    nm=c.element_info.name or ''
                    if 'create' in nm.lower() and 'apple' in nm.lower():
                        log('UIA_BTN',c.element_info.control_type,repr(nm)[:120])
                        try: c.invoke(); log('UIA_INVOKE_OK'); got=True
                        except Exception as e:
                            log('UIA_INVOKE_ERR',repr(e)[:120])
                            try: c.click_input(); log('UIA_CLICKINPUT_OK'); got=True
                            except Exception as e2: log('UIA_CLICKINPUT_ERR',repr(e2)[:120])
                        break
                except Exception: pass
            if not got: log('UIA_BTN_NOTFOUND')
            time.sleep(5); shot('p10_C_after_uia'); dump_all_windows(pid,'p10_C')
    tl1=tasklist(); log('NEW_PROC',json.dumps(sorted(tl1-tl0),ensure_ascii=False)[:1200])
    # 4) watch 60s for any creation window (visible or not) and dump UIA trees
    t0=time.time(); seen_all=set(w['hwnd'] for w in all_win_enum())
    for t in range(10):
        time.sleep(6); shot('p10_watch_%d'%t)
        for ww in all_win_enum():
            if ww['hwnd'] not in seen_all:
                seen_all.add(ww['hwnd'])
                log('NEW_WIN_%d'%t, ww['pid'], ww['visible'], ww['title'], ww['class'], ww['rect'])
        for ww in [w for w in all_win_enum() if w['pid']==pid]:
            dump_tree(ww['hwnd'],'p10_t%d_%s'%(t,re.sub(r'\W+','_',(ww['title'] or ww['class'] or 'x')[:20])),8,900)
        if time.time()-t0>70: break
    pat=re.compile(r'virtual\s*machine|not\s+supported|cannot\s+be\s+created|not\s+available|captcha|verification|image\s+code|birth|country|first\s+name|last\s+name|password|email|apple id|apple account|create',re.I)
    hits=[]
    for w in all_win_enum():
        if w['pid']!=pid: continue
        try: desc=d.window(handle=w['hwnd']).descendants()
        except Exception: desc=[]
        for c in desc:
            try:
                nm=c.element_info.name or ''
                if pat.search(nm): hits.append((w['title'][:20],w['visible'],c.element_info.control_type,nm[:120]))
            except Exception: pass
    log('FINAL_TEXT_HITS',json.dumps(hits[:80],ensure_ascii=False)[:5000])
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
if __name__=='__main__':
    try: main()
    except Exception: log('FATAL',traceback.format_exc())
