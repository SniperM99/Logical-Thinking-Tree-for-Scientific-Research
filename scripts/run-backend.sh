#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ -d "$base/.runtime/jdk-21.jdk/Contents/Home" ]; then
  JAVA_HOME="$base/.runtime/jdk-21.jdk/Contents/Home"; export JAVA_HOME
  PATH="$JAVA_HOME/bin:$PATH"; export PATH
fi
if [ -f "$base/backend/target/research-core-0.1.0.jar" ]; then exec java -jar "$base/backend/target/research-core-0.1.0.jar"; fi
cd "$base/backend"
if command -v mvn >/dev/null 2>&1; then runner=mvn; else runner="$base/.runtime/apache-maven-3.9.9/bin/mvn"; fi
if [ -f "$base/.runtime/maven-settings.xml" ]; then exec "$runner" -s "$base/.runtime/maven-settings.xml" spring-boot:run; fi
exec "$runner" spring-boot:run
