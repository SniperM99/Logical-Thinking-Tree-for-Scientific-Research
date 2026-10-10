#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ -d "$base/.runtime/jdk-21.jdk/Contents/Home" ]; then
  JAVA_HOME="$base/.runtime/jdk-21.jdk/Contents/Home"; export JAVA_HOME
  PATH="$JAVA_HOME/bin:$PATH"; export PATH
fi
if command -v mvn >/dev/null 2>&1; then runner=mvn; else runner="$base/.runtime/apache-maven-3.9.9/bin/mvn"; fi
cd "$base/backend"
if [ "$#" -eq 0 ]; then set -- package; fi
if [ -f "$base/.runtime/maven-settings.xml" ]; then exec "$runner" -s "$base/.runtime/maven-settings.xml" "$@"; fi
exec "$runner" "$@"
