"""Launch the persistent local service, then open its fixed address."""
import json, os, pathlib, subprocess, sys, time, urllib.request, webbrowser
root=pathlib.Path(__file__).resolve().parent
port=int(os.environ.get('JOB_COMPASS_OSS_PORT','18866'))
url=f'http://127.0.0.1:{port}'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def healthy():
    try:
        with opener.open(url+'/api/health',timeout=2) as r:return json.load(r).get('app')=='job-compass-open-source'
    except Exception:return False
if not healthy():
    pythonw=pathlib.Path(sys.executable).with_name('pythonw.exe')
    subprocess.Popen([str(pythonw if pythonw.exists() else pathlib.Path(sys.executable)),str(root/'app.py')],cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(40):
        if healthy():break
        time.sleep(.25)
if healthy():webbrowser.open(url)
else:
    message=f'Job Compass could not start. Check port {port}, or run python app.py to see the error.'
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,message,'Job Compass',0)
    else:
        print(message,file=sys.stderr)
