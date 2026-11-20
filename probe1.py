import os, sys, time, json, traceback, ctypes, subprocess, urllib.request, urllib.error, re
OUT=os.path.abspath('out'); os.makedirs(OUT,exist_ok=True)
LOG=open(os.path.join(OUT,'probe_out.log'),'w',encoding='utf-8')
def log(*a):
    s=' '.join(str(x) for x in a)
    print(s); LOG.write(s+'\n'); LOG.flush()
def shot(name):
    try:
        from PIL import ImageGrab
        im=ImageGrab.grab(all_screens=True)
        p=os.path.join(OUT,name+'.png'); im.save(p); log('SHOT',name,im.size)
        return p
    except Exception as e:
        log('SHOT_ERR',name,repr(e)); return None

def net_probe():
    urls=['https://api.ipify.org?format=json','http://ip-api.com/json',
          'https://api.mail.tm/domains','https://www.1secmail.com/api/v1/?action=getDomainList',
          'https://asms.ai/number/447450699185','https://account.apple.com/']
    for u in urls:
        try:
            req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req,timeout=25) as r:
                b=r.read(300000); log('NET',u,r.status,len(b),repr(b[:400]))
        except Exception as e:
            log('NET_ERR',u,repr(e)[:200])

def find_exe():
    for c in [r'C:\Program Files\iTunes\iTunes.exe', r'C:\Program Files (x86)\iTunes\iTunes.exe']:
        if os.path.exists(c): return c
    for root in [r'C:\Program Files', r'C:\Program Files (x86)']:
        for dp,dn,fn in os.walk(root):
            if 'WindowsApps' in dp: continue
            for f in fn:
                if f.lower()=='itunes.exe': return os.path.join(dp,f)
    return None

def list_windows():
    from pywinauto import Desktop
    res=[]
    try:
        d=Desktop(backend='uia')
        for w in d.windows():
            try:
                e=w.element_info
                res.append({'title':w.window_text(),'class':e.class_name,'type':e.control_type,'handle':w.handle,'obj':w})
            except Exception as ex:
                res.append({'title':'?','class':'?','type':'?','handle':0,'obj':w})
    except Exception as e:
        log('LISTWIN_ERR',repr(e))
    return res

def walk(ctrl, maxdepth=10, d=0):
    yield ctrl
    if d>=maxdepth: return
    try: ch=ctrl.children()
    except Exception: return
    for c in ch:
        yield from walk(c, maxdepth, d+1)

def dump(ctrl, tag, maxdepth=8, maxlines=2000):
    lines=[]
    def rec(c,d):
        if len(lines)>=maxlines: return
        try:
            i=c.element_info
            lines.append('%s[%s] class=%r name=%r aid=%r'%('  '*d,i.control_type,i.class_name,(i.name or '')[:150],i.automation_id))
        except Exception:
            return
        if d<maxdepth:
            try: ch=c.children()
            except Exception: ch=[]
            for x in ch: rec(x,d+1)
    rec(ctrl,0)
    p=os.path.join(OUT,tag+'.txt'); open(p,'w',encoding='utf-8').write('\n'.join(lines))
    log('DUMP',tag,len(lines)); return lines

def find_named(root, subs, maxdepth=10):
    out=[]
    for c in walk(root,maxdepth):
        try: n=(c.element_info.name or '')
        except Exception: continue
        nl=n.lower()
        if any(s in nl for s in subs): out.append((c,n))
    return out

def click(c):
    try:
        c.invoke(); log('CLICK invoke ok'); return True
    except Exception:
        pass
    try:
        c.click_input(); log('CLICK input ok'); return True
    except Exception as e:
        log('CLICK_ERR',repr(e)[:150]); return False

def dump_menu(hwnd):
    u=ctypes.windll.user32
    hm=u.GetMenu(hwnd); out=[]
    if not hm: return out
    n=u.GetMenuItemCount(hm)
    for i in range(n):
        buf=ctypes.create_unicode_buffer(512); u.GetMenuStringW(hm,i,buf,512,0x400)
        entry={'text':buf.value,'id':u.GetMenuItemID(hm,i),'items':[]}
        sub=u.GetSubMenu(hm,i)
        if sub:
            m=u.GetMenuItemCount(sub)
            for j in range(m):
                b2=ctypes.create_unicode_buffer(512); u.GetMenuStringW(sub,j,b2,512,0x400)
                entry['items'].append({'text':b2.value,'id':u.GetMenuItemID(sub,j)})
        out.append(entry)
    return out

def post_cmd(hwnd,cid):
    ctypes.windll.user32.PostMessageW(hwnd,0x111,cid,0)
    log('POST_CMD',hex(cid))

def main():
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    log('START',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    net_probe()
    exe=find_exe(); log('ITUNES_EXE',exe)
    if not exe:
        log('ABORT no itunes exe'); return
    try:
        log('VERSION',repr(subprocess.check_output(['powershell','-NoProfile','-Command',"(Get-Item '%s').VersionInfo | Format-List | Out-String"%exe]).decode(errors='replace')[:500]))
    except Exception as e: log('VER_ERR',repr(e)[:200])
    shot('s0_desktop')
    log('LAUNCH')
    p=subprocess.Popen([exe])
    time.sleep(35)
    shot('s0b_after_launch')
    # onboarding dialogs
    for it in range(8):
        ws=list_windows()
        log('WINDOWS_%d'%it, json.dumps([(x.get('title'),x.get('class'),x.get('type')) for x in ws],ensure_ascii=False)[:2000])
        handled=False
        for x in ws:
            t=(x.get('title') or '').lower()
            if any(k in t for k in ['license','agreement','welcome','setup','software','itunes']):
                tag='w%d_%s'%(it, re.sub(r'\W+','_',t)[:24])
                try:
                    dump(x['obj'],tag,maxdepth=5,maxlines=600)
                    shot(tag)
                except Exception as e: log('DMPERR',repr(e)[:100])
                cands=[c for c,n in find_named(x['obj'],['agree','accept','continue','get started','next','ok'])]
                for c in cands:
                    if click(c): handled=True; break
        if handled:
            time.sleep(6); shot('s_onboard_%d'%it); continue
        break
    # find main window
    main_win=None
    for x in list_windows():
        if (x.get('title') or '').strip().lower() in ('itunes','itunes 12'):
            main_win=x; break
    if not main_win:
        for x in list_windows():
            if 'itunes' in (x.get('title') or '').lower(): main_win=x; break
    if not main_win:
        log('NO_MAIN_WINDOW'); shot('s_nomain'); return
    log('MAINWIN',main_win['title'],main_win['class'],hex(main_win['handle']))
    hwnd=main_win['handle']
    try:
        menu=dump_menu(hwnd)
        open(os.path.join(OUT,'menu.json'),'w',encoding='utf-8').write(json.dumps(menu,ensure_ascii=False,indent=1))
        log('MENU',json.dumps(menu,ensure_ascii=False)[:3000])
    except Exception as e:
        menu=[]; log('MENU_ERR',repr(e)[:200])
    dump(main_win['obj'],'main_tree',maxdepth=6,maxlines=1200)
    shot('s1_main')
    # click Account -> Sign In
    cid=None
    for m in menu:
        if 'account' in (m['text'] or '').lower().replace('&',''):
            for it in m['items']:
                if 'sign' in (it['text'] or '').lower(): cid=it['id']
    if cid is None:
        for m in menu:
            for it in m['items']:
                if 'sign' in (it['text'] or '').lower(): cid=it['id']; log('SIGNIN_ALT_MENU',m['text'],it)
    if cid is not None:
        log('SIGNIN_CID',cid); post_cmd(hwnd,cid); time.sleep(15)
    else:
        log('NO_SIGNIN_MENU_ITEM')
    shot('s2_after_signin')
    ws=list_windows()
    log('WINDOWS_AFTER_SIGNIN', json.dumps([(x.get('title'),x.get('class'),x.get('type')) for x in ws],ensure_ascii=False)[:2000])
    for idx,x in enumerate(ws):
        tag='signin_w%d_%s'%(idx, re.sub(r'\W+','_',(x.get('title') or '')[:24]))
        try: dump(x['obj'],tag,maxdepth=6,maxlines=900)
        except Exception as e: log('DMPERR',repr(e)[:100])
    try: dump(main_win['obj'],'main_tree_after_signin',maxdepth=7,maxlines=1500)
    except Exception: pass
    # search create entry
    found=[]
    for x in list_windows():
        for c,n in find_named(x['obj'],['create'],maxdepth=10):
            found.append((x.get('title'),n,c))
    log('CREATE_FOUND', json.dumps([(t,n) for t,n,_ in found],ensure_ascii=False)[:2000])
    if found:
        shot('s3_before_create')
        click(found[0][2]); time.sleep(15); shot('s4_after_create')
        ws=list_windows()
        log('WINDOWS_AFTER_CREATE', json.dumps([(x.get('title'),x.get('class'),x.get('type')) for x in ws],ensure_ascii=False)[:2000])
        for idx,x in enumerate(ws):
            tag='create_w%d_%s'%(idx, re.sub(r'\W+','_',(x.get('title') or '')[:24]))
            try: dump(x['obj'],tag,maxdepth=6,maxlines=900)
            except Exception: pass
    log('DONE',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))

if __name__=='__main__':
    try: main()
    except Exception:
        log('FATAL',traceback.format_exc())
