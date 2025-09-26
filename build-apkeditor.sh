#!/bin/bash

## TOMER NOTE: CURRENTLY THIS IS NOT WORKING GREAT BECAUSE JAVA SHIT

echo "Initializing submodules..."
git submodule update --init --recursive

echo "Building APKEditor..."
cd libs/APKEditor

# Make gradlew executable
chmod +x gradlew

# Build APKEditor
./gradlew build

# Copy the built JAR to a more accessible location
cd ../..
cp libs/APKEditor/app/build/libs/*.jar libs/APKEditor/APKEditor.jar

echo "APKEditor built successfully!"
