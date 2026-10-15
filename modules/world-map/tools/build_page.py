"""Junta web/index.html + web/map.js numa única página para publicar (dist/praga-mapa.html)."""
import re, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
src = (ROOT / 'web/index.html').read_text()
js = (ROOT / 'web/map.js').read_text()
head = re.search(r'<head>(.*?)</head>', src, re.S).group(1)
body = re.search(r'<body>(.*?)</body>', src, re.S).group(1)
head = re.sub(r'<meta charset="utf-8">\s*', '', head)
head = re.sub(r'<meta name="viewport"[^>]*>\s*', '', head)
head = head.replace('<title>Praga — Mapa</title>', '<title>Mapa da Praga</title>\n<meta name="claude:viewport-fit-sides" content="cover">')
head = head.replace('html, body { margin: 0; height: 100%;', 'html, body { margin: 0; height: 100%; color-scheme: dark;')
head = head.replace('</style>', '''
  #title { top: calc(16px + env(safe-area-inset-top, 0px)); left: max(16px, env(safe-area-inset-left, 0px)); }
  #legend { bottom: calc(16px + env(safe-area-inset-bottom, 0px)); left: max(16px, env(safe-area-inset-left, 0px)); }
  #info { top: calc(16px + env(safe-area-inset-top, 0px)); right: max(16px, env(safe-area-inset-right, 0px)); }
  #log { bottom: calc(16px + env(safe-area-inset-bottom, 0px)); right: max(16px, env(safe-area-inset-right, 0px)); }
  @media (max-width: 720px) {
    #title { right: max(16px, env(safe-area-inset-right, 0px)); }
    #info { top: auto; bottom: calc(16px + env(safe-area-inset-bottom, 0px)); left: max(16px, env(safe-area-inset-left, 0px)); right: max(16px, env(safe-area-inset-right, 0px)); }
  }
  @media (prefers-reduced-motion: reduce) { #hint { display: none; } }
</style>''')
body = body.replace('<script type="module" src="map.js"></script>', '<script type="module">\n' + js + '\n</script>')
out = ROOT / 'build' / 'dist'; out.mkdir(parents=True, exist_ok=True)
(out / 'praga-mapa.html').write_text(head.strip() + '\n' + body.strip() + '\n')
print('ok', (out / 'praga-mapa.html').stat().st_size)
