"""Compile the preserved Java adapter against the prepared pinned Yamcs classpath."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
work = Path(sys.argv[1]).resolve()
java = Path(os.environ['JAVA'])
javac = java.with_name('javac' + java.suffix)
classes = work / 'compiled_v2'
classes.mkdir(exist_ok=True)
subprocess.run([str(javac), '-cp', os.environ['YAMCS_CLASSPATH'], '-d', str(classes),
                str(work / 'VirtualPeerV2.java')], check=True)
