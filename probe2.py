import os, sys, time, json, traceback, ctypes, subprocess, urllib.request, re
from ctypes import wintypes
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe2_out.log'),'w',encoding='utf-8')
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
                res.append({'hwnd':int(h),'title':b.value,'class':c.value,'rect':(r.left,r.top,r.right,r.bottom),'pid':wintypes.DWORD()})
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

def click_rect(cx,cy):
    u.SetCursorPos(int(cx),int(cy)); time.sleep(0.3)
    u.mouse_event(0x0002,0,0,0,0); time.sleep(0.08); u.mouse_event(0x0004,0,0,0,0); log('MOUSE',cx,cy)

def send_cmd(hwnd,cid):
    log('WM_COMMAND',hex(int(hwnd)),cid); u.PostMessageW(int(hwnd),0x111,cid,0)

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
                e['items'].append({'text':b2.value,'id':int(u.GetMenuItemID(sub,j))})
        out.append(e)
    return out

def uia_dump(handle, tag, maxdepth=7, maxlines=1500):
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

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    exe=find_exe(); log('EXE',exe)
    if not exe: return
    p=subprocess.Popen([exe]); log('PID',p.pid)
    time.sleep(25)
    shot('p2_s0_launch')
    # accept EULA rounds
    for it in range(12):
        ws=win_enum()
        log('W%d'%it, json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:1800])
        dlg=[w for w in ws if 'license agreement' in (w['title'] or '').lower()]
        if not dlg: break
        h=dlg[0]['hwnd']; kids=child_enum(h)
        btns=[k for k in kids if (k['title'] or '').strip().lower() in ('agree','accept','i agree')]
        log('EULA_KIDS', json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:1500])
        if not btns: log('NO_AGREE_BTN'); break
        b=btns[0]; r=b['rect']; cx=(r[0]+r[2])//2; cy=(r[1]+r[3])//2
        log('AGREE_BTN',b['title'],b['id'],r)
        u.SetForegroundWindow(h); time.sleep(0.6)
        if r[2]>r[0] and r[3]>r[1]:
            click_rect(cx,cy); time.sleep(3)
        if any('license agreement' in (w['title'] or '').lower() for w in win_enum()):
            send_cmd(h, b['id'] if b['id']>0 else 1); time.sleep(3)
        shot('p2_eula_%d'%it)
    # main window
    ws=win_enum()
    log('AFTER_EULA', json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2000])
    main_w=None
    for w in ws:
        if (w['title'] or '').strip().lower()=='itunes': main_w=w; break
    if not main_w:
        for w in ws:
            if 'itunes' in (w['title'] or '').lower() and 'license' not in (w['title'] or '').lower(): main_w=w; break
    if not main_w:
        log('NO_MAIN'); shot('p2_nomain'); return
    log('MAIN', main_w)
    hwnd=main_w['hwnd']
    menu=dump_menu(hwnd); open(os.path.join(OUT,'menu2.json'),'w').write(json.dumps(menu,ensure_ascii=False,indent=1))
    log('MENU', json.dumps(menu,ensure_ascii=False)[:3000])
    u.SetForegroundWindow(hwnd); time.sleep(1); shot('p2_main'); uia_dump(hwnd,'p2_main_tree',6,1200)
    # Account -> Sign In
    cid=None
    for m in menu:
        if 'account' in (m['text'] or '').lower().replace('&',''):
            for it in m['items']:
                if 'sign' in (it['text'] or '').lower(): cid=it['id']; log('SIGNIN_ITEM',it)
    if cid is None:
        for m in menu:
            for it in m['items']:
                if 'sign' in (it['text'] or '').lower(): cid=it['id']; log('SIGNIN_ANY',m['text'],it)
    if cid is not None: send_cmd(hwnd,cid)
    else: log('NO_SIGNIN_ITEM')
    time.sleep(18); shot('p2_after_signin')
    ws=win_enum(); log('AFTER_SIGNIN', json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2000])
    for w in ws:
        if 'itunes' in (w['title'] or '').lower() or 'apple' in (w['title'] or '').lower():
            kids=child_enum(w['hwnd'])
            log('KIDS',w['title'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:3000])
            uia_dump(w['hwnd'],'p2_win_%s'%re.sub(r'\W+','_',(w['title'] or 'x')[:24]),6,1200)
    # find create button
    cand=[]
    for w in win_enum():
        for k in child_enum(w['hwnd']):
            t=(k['title'] or '').strip()
            if t and re.search(r'create',t,re.I) and 'paging' not in t.lower():
                cand.append((w,k))
    log('CREATE_NATIVE', json.dumps([(w['title'],k['title'],k['class'],k['id'],k['rect']) for w,k in cand],ensure_ascii=False)[:1500])
    clicked=False
    if cand:
        w,k=cand[0]; u.SetForegroundWindow(w['hwnd']); time.sleep(0.5)
        r=k['rect']
        if r[2]>r[0] and r[3]>r[1]: click_rect((r[0]+r[2])//2,(r[1]+r[3])//2); clicked=True
        elif k['id']>0: send_cmd(w['hwnd'],k['id']); clicked=True
    if not clicked:
        try:
            from pywinauto import Desktop
            d=Desktop(backend='uia')
            for w in d.windows():
                try: n=(w.window_text() or '')
                except Exception: continue
                if 'itunes' not in n.lower(): continue
                for c in w.descendants():
                    try: nm=(c.element_info.name or '').lower()
                    except Exception: continue
                    if 'create' in nm and 'new apple' in nm:
                        log('UIA_CREATE',nm); c.click_input(); clicked=True; break
                if clicked: break
        except Exception as e: log('UIA_CREATE_ERR',repr(e)[:150])
    time.sleep(15); shot('p2_after_create')
    ws=win_enum(); log('AFTER_CREATE', json.dumps([(w['title'],w['class'],w['rect']) for w in ws],ensure_ascii=False)[:2000])
    for w in ws:
        if 'itunes' in (w['title'] or '').lower() or 'apple' in (w['title'] or '').lower() or 'account' in (w['title'] or '').lower():
            kids=child_enum(w['hwnd'])
            log('CKIDS',w['title'], json.dumps([(k['class'],k['title'],k['id'],k['rect'],k['visible']) for k in kids],ensure_ascii=False)[:4000])
            uia_dump(w['hwnd'],'p2_cwin_%s'%re.sub(r'\W+','_',(w['title'] or 'x')[:24]),7,1800)
            shot('p2_cwin_%s'%re.sub(r'\W+','_',(w['title'] or 'x')[:24]))
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))

if __name__=='__main__':
    try: main()
    except Exception: log('FATAL',traceback.format_exc())
