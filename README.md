# AnotherApkPatcher

A comprehensive Python tool for decompiling, modifying, and re-signing Android APK files. This tool automates the entire APK reverse engineering workflow with support for automated file patching or interactive modification.

## Features

- **Full APK Processing Pipeline**: Decompile, modify, recompile, align, and sign APKs
- **Flexible Patching Options**: 
  - Interactive mode for manual file modifications
  - Automated JSON-based file patching
- **Secure Key Management**: Generate new keystores or use existing ones
- **Clean Workflow**: Automatic cleanup of temporary files
- **Comprehensive Logging**: Detailed console and file-based logging
- **Error Handling**: Robust error handling with proper cleanup

## Prerequisites

Before using AnotherApkPatcher, ensure you have the following tools installed:

1. **Android SDK Tools**:
   - `apktool.jar` - For APK decompilation/recompilation
   - `apksigner.jar` - For APK signing
   - `zipalign` - For APK alignment

2. **Java Development Kit (JDK)** - Required for running the tools

3. **Python 3.6+** - With the `toml` package installed:
   ```bash
   pip install toml
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AnotherApkPatcher.git
   cd AnotherApkPatcher
   ```

2. Install Python dependencies:
   ```bash
   pip install toml
   ```

3. Download the required Android tools and place them in a `tools` directory:
   ```bash
   mkdir tools
   # Place apktool.jar, apksigner.jar, and zipalign in this directory
   ```

## Usage

### Basic Usage

```bash
python apk_processor.py app.apk
```

This will:
1. Decompile the APK
2. Enter interactive mode for file modifications
3. Recompile, align, and sign the APK
4. Output the signed APK as `app_signed.apk`

### Automated File Patching

Create a JSON patches file (`apk_file_patches.json`):

```json
{
  "patch": [
    {
      "src": "/path/to/local/config.xml",
      "dest": "res/xml/config.xml"
    },
    {
      "src": "/path/to/local/smali/MainActivity.smali",
      "dest": "smali/com/example/MainActivity.smali"
    }
  ]
}
```

Then run with automated patching:
```bash
python apk_processor.py app.apk --apk-file-patches patches.json
```

### Command Line Options

```bash
usage: apk_processor.py [-h] [--tools-dir TOOLS_DIR] [--log-file LOG_FILE]
                        [--keystore KEYSTORE] [--alias ALIAS]
                        [--password PASSWORD] [--output OUTPUT]
                        [--interactive | --apk-file-patches APK_FILE_PATCHES]
                        apk_path

APK Decompiler and Re-signer

positional arguments:
  apk_path              Path to the APK file to process

optional arguments:
  -h, --help            show this help message and exit
  --tools-dir TOOLS_DIR
                        Directory containing tools (default: ./tools)
  --log-file LOG_FILE   Path to log file (if not provided, logging to file is
                        disabled)
  --keystore KEYSTORE   Path to existing keystore (if not provided, a new one
                        will be generated)
  --alias ALIAS         Key alias (default: key0)
  --password PASSWORD   Keystore and key password (default: android)
  --output OUTPUT       Output APK path (default: <original_name>_signed.apk)
  --interactive         Interactive file modification mode
  --apk-file-patches APK_FILE_PATCHES
                        JSON file containing APK file patches (default:
                        apk_file_patches.json)
```

## Workflow

1. **Decompilation**: The APK is decompiled using apktool
2. **Modification**: 
   - Interactive: User manually modifies files in the decompiled directory
   - Automated: Files are patched based on the JSON configuration
3. **Recompilation**: The modified sources are recompiled into a new APK
4. **Alignment**: The APK is aligned using zipalign for optimal performance
5. **Signing**: The APK is signed with either:
   - A newly generated keystore
   - An existing keystore provided by the user
6. **Cleanup**: All temporary files are automatically removed

## JSON Patches Format

The patches JSON file should contain a `patch` array with objects specifying source and destination paths:

```json
{
  "patch": [
    {
      "src": "/absolute/path/to/local/file.txt",
      "dest": "relative/path/in/apk/file.txt"
    }
  ]
}
```

- `src`: Path to the file on your local system
- `dest`: Path where the file should be placed in the decompiled APK directory

If the patches file doesn't exist, AnotherApkPatcher will automatically create an example file for you to modify.

## Examples

### Using an Existing Keystore
```bash
python apk_processor.py app.apk --keystore mykey.jks --password mypassword
```

### Custom Output Path
```bash
python apk_processor.py app.apk --output modified_app.apk
```

### Custom Tools Directory
```bash
python apk_processor.py app.apk --tools-dir /path/to/android/tools
```

### Enable File Logging
```bash
python apk_processor.py app.apk --log-file processing.log
```

## Security Notes

- Passwords are handled securely and not stored in logs
- Temporary files are automatically cleaned up after processing
- When generating new keystores, a default distinguished name is used

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is intended for legitimate security research, educational purposes, and authorized testing only. Users are responsible for complying with all applicable laws and regulations. The authors are not responsible for any misuse of this tool.
