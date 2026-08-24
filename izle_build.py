"""Apprentice-Izleyici.exe uretimi (konsolsuz): python izle_build.py"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(ROOT, "build", "izleyici")
cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--windowed",
       "--name", "Apprentice-Izleyici",
       "--icon", os.path.join(ROOT, "assets", "apprentice.ico"),   # ortak Apprentice ikonu
       "--distpath", os.path.join(ROOT, "dist"), "--workpath", BUILD, "--specpath", BUILD,
       os.path.join(ROOT, "izle.py")]
raise SystemExit(subprocess.run(cmd).returncode)
