# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['555.py'],
    pathex=[],
    binaries=[],
    datas=[(r'C:\Users\l3ere\AppData\Local\Programs\Python\Python313\Lib\site-packages\streamlit\static', 'streamlit/static'),
    (r'C:\Users\l3ere\AppData\Local\Programs\Python\Python313\Lib\site-packages\streamlit\components', 'streamlit/components'), # ถ้าได้เพิ่มอันนี้ไว้
    # --- !!! เพิ่มบรรทัดนี้ !!! ---
    (r'C:\Users\l3ere\AppData\Local\Programs\Python\Python313\Lib\site-packages\streamlit-1.45.0.dist-info', 'streamlit-1.45.0.dist-info')
    # ^--- แก้ Path และชื่อโฟลเดอร์ให้ตรงกับที่คุณเจอจริงๆ   ^--- ใช้ชื่อโฟลเดอร์เดียวกันเป็น Destination
],
    hiddenimports=['streamlit.web.server.app_session', 'streamlit.web.server.server', 'streamlit.runtime', 'streamlit.runtime.caching', 	'streamlit.runtime.scriptrunner', 'validators', 'watchdog', 'pandas', 'numpy', 'google', 'google.api_core', 'google.protobuf', 'google.auth', 	'PIL', 'pyarrow', 'altair'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI_Metadata_App',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI_Metadata_App',
)
