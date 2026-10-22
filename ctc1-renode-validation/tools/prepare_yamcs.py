"""Prepare a pinned public Yamcs build; no dependency on another research folder."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / '.deps'
PIN = 'ee4c33f1650f9fae84d9a932bea4d57d6c9b2bbb'
record = DEPS / 'yamcs-classpath.json'

def classpath_jar(entries):
    # Manifest wrapping keeps Windows process command lines short.
    line = 'Class-Path: ' + ' '.join(path.as_uri() + ('/' if path.is_dir() else '') for path in entries)
    manifest = 'Manifest-Version: 1.0\r\n'
    while line:
        manifest += line[:70] + '\r\n'
        line = ' ' + line[70:] if len(line) > 70 else ''
    with zipfile.ZipFile(DEPS / 'yamcs-dependencies.jar', 'w') as archive:
        archive.writestr('META-INF/MANIFEST.MF', manifest + '\r\n')

if record.exists():
    cp = json.loads(record.read_text())
    if all((ROOT / x).exists() for x in cp):
        classpath_jar([ROOT / x for x in cp])
        print('Local pinned Yamcs classpath ready.')
        raise SystemExit(0)
java = Path(os.environ['JAVA'])
env = os.environ.copy()
env['JAVA_HOME'] = str(java.parent.parent)
env['PATH'] = str(java.parent) + os.pathsep + env.get('PATH', '')
maven = env.get('MAVEN') or shutil.which('mvn') or shutil.which('mvn.cmd')
if not maven:
    raise SystemExit('Install Maven 3.9+ or set MAVEN to mvn/mvn.cmd. Java 17+ is required.')
source = DEPS / ('yamcs-' + PIN)
if not source.exists():
    archive = DEPS / 'yamcs.zip'
    urllib.request.urlretrieve('https://codeload.github.com/yamcs/yamcs/zip/' + PIN, archive)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if not (DEPS / member.filename).resolve().is_relative_to(DEPS.resolve()):
                raise SystemExit('Unsafe Yamcs archive path')
        z.extractall(DEPS)
local_repo = DEPS / 'm2'
base = [str(maven), '-q', '-Dmaven.repo.local=' + str(local_repo), '-DskipTests']
subprocess.run(base + ['-pl', 'yamcs-core', '-am', 'install'], cwd=source, env=env, check=True)
cp_file = DEPS / 'maven-classpath.txt'
subprocess.run(base + ['-pl', 'yamcs-core', 'dependency:build-classpath',
                      '-Dmdep.includeScope=test', '-Dmdep.outputFile=' + str(cp_file)],
               cwd=source, env=env, check=True)
entries = [source / 'yamcs-core/target/test-classes', source / 'yamcs-core/target/classes']
entries += [Path(x) for x in cp_file.read_text().strip().split(os.pathsep) if x]
if not all(path.exists() for path in entries):
    raise SystemExit('Yamcs classpath contains a missing entry')
record.write_text(json.dumps([str(x.relative_to(ROOT)) for x in entries], indent=2), encoding='utf-8')
classpath_jar(entries)
print('Pinned Yamcs dependencies built locally.')
