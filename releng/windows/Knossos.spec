# -*- mode: python -*-
## Copyright 2015 Knossos authors, see NOTICE file
##
## Licensed under the Apache License, Version 2.0 (the "License");
## you may not use this file except in compliance with the License.
## You may obtain a copy of the License at
##
##     http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing, software
## distributed under the License is distributed on an "AS IS" BASIS,
## WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
## See the License for the specific language governing permissions and
## limitations under the License.

import sys
import os.path
import re
import PyQt5

onefile = False
him = []
debug = os.environ.get('KN_BUILD_DEBUG') == 'yes'

# Build the TaskbarLib module.
try:
    import comtypes.client as cc
    cc.GetModule('support/taskbar.tlb')

    import comtypes.gen as cg
    gen_path = os.path.dirname(cg.__file__)

    for fname in os.listdir(gen_path):
        if not fname.startswith('__'):
            him.append('comtypes.gen.' + fname.split('.')[0])
except:
    import logging
    logging.exception('Failed to generate comtypes.gen.TaskbarLib!')

rthooks = []
if debug:
    rthooks.append('../../tools/common/debug-rthook.py')

qt_path = os.path.dirname(PyQt5.__file__)
qt_bin = os.path.join(qt_path, 'qt', 'bin')

with open('../../knossos/center.py') as stream:
    match = re.search(r"VERSION = '([^']+)'", stream.read())

if not match:
    print('ERROR: Could not determine version!')
    sys.exit(1)

version = match.group(1)
if '-dev' in version:
    if not os.path.exists('../../.git'):
        print('\nWARNING: No .git directory found while building a devbuild!\n')
    else:
        with open('../../.git/HEAD') as stream:
            ref = stream.read().strip().split(':')
            assert ref[0] == 'ref'

        with open('../../.git/' + ref[1].strip()) as stream:
            version += '+' + stream.read()[:7]

with open('version', 'w') as stream:
    stream.write(version)

a = Analysis(['../../knossos/__main__.py'],
            pathex=['../..', 'py-env/lib/site-packages/PyQt5/qt/bin'],
            hiddenimports=him,
            hookspath=['../../tools/common'],
            runtime_hooks=rthooks,
            datas=[
                ('version', '.'),
                ('../../knossos/data/hlp.ico', 'data'),
                ('../../knossos/data/resources.rcc', 'data'),
                (os.path.join(qt_path, 'qt', 'resources'), '.')
            ])

# Exclude everything we don't need.
idx = []
for i, item in enumerate(a.binaries):
    fn = item[0].lower()
    if fn.startswith(('ole', 'user32')):
        idx.append(i)

for i in reversed(idx):
    del a.binaries[i]

idx = []
for i, item in enumerate(a.pure):
    if item[0].startswith(('pydoc', 'pycparser')):
        idx.append(i)
    elif item[0] == 'comtypes.client._code_cache':
        a.pure[i] = (item[0], './comtypes_code_cache.py', item[2])

for i in reversed(idx):
    del a.pure[i]

pyz = PYZ(a.pure)

a.datas += [('7z.exe', 'support/7z.exe', 'BINARY'),
            ('7z.dll', 'support/7z.dll', 'BINARY'),
            ('SDL2.dll', 'support/SDL2.dll', 'BINARY'),
            ('openal.dll', 'support/openal.dll', 'BINARY'),
            ('taskbar.tlb', 'support/taskbar.tlb', 'BINARY')]

for name in ('QtWebEngineProcess.exe', 'libEGL.dll', 'libGLESv2.dll'):
    a.datas.append((name, os.path.join(qt_bin, name), 'BINARY'))


if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
              exclude_binaries=False,
              name='Knossos.exe',
              icon='../../knossos/data/hlp.ico',
              debug=False,
              strip=None,
              upx=False,
              console=debug)
else:
    exe = EXE(pyz,
              a.scripts,
              exclude_binaries=True,
              name='Knossos.exe',
              icon='../../knossos/data/hlp.ico',
              debug=False,
              strip=None,
              upx=not debug,
              console=debug)

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=None,
                   upx=False,  # upx breaks Qt somehow
                   name='Knossos')
