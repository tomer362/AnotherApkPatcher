@echo off
REM build.bat

echo Initializing submodules...
git submodule update --init --recursive

echo Building APKEditor...
cd libs\APKEditor

REM Build APKEditor
gradlew.bat build

REM Copy the built JAR to a more accessible location
cd ..\..
copy libs\APKEditor\app\build\libs\*.jar libs\APKEditor\APKEditor.jar

echo APKEditor built successfully!
