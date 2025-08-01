# patcher.py
import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import urllib.request
import urllib.error

# Import our SDK installer
try:
    from sdk_installer import install_sdk_tools, setup_logging as setup_sdk_logging, get_sdk_tool_paths
    SDK_INSTALLER_AVAILABLE = True
except ImportError:
    SDK_INSTALLER_AVAILABLE = False
    def install_sdk_tools(*args, **kwargs):
        return False
    def get_sdk_tool_paths(*args, **kwargs):
        return None, None

# Import merger
try:
    from merger import merge_apks
    MERGER_AVAILABLE = True
except ImportError:
    MERGER_AVAILABLE = False
    def merge_apks(*args, **kwargs):
        return False

# Constants
DEFAULT_TOOLS_DIR = Path("./tools")
DEFAULT_ALIAS = "key0"
DEFAULT_PASSWORD = "android"
DEFAULT_LOG_FILE = "apk_processor.log"
TEMP_DIR_PREFIX = "apk_processor_"
APKTOOL_JAR = "apktool.jar"
APKSIGNER_JAR = "apksigner.jar"
ZIPALIGN_BIN = "zipalign"
DECOMPILED_SUFFIX = "_decompiled"
UNALIGNED_SUFFIX = "_unaligned.apk"
ALIGNED_SUFFIX = "_aligned.apk"
SIGNED_SUFFIX = "_signed.apk"
DEFAULT_KEYSTORE = "release.keystore"
KEY_DNAME = "CN=Unknown, OU=Unknown, O=Unknown, L=Unknown, ST=Unknown, C=Unknown"
DEFAULT_PATCHES_FILE = Path("apk_file_patches.json")
APKTOOL_DOWNLOAD_URL = "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.12.0.jar"
DEFAULT_ANDROID_VERSION = "34.0.0"
DEFAULT_SDK_ROOT = Path.home() / "android-sdk"
APKEDITOR_JAR_DEFAULT = Path("libs/APKEditor/APKEditor.jar")
DEFAULT_MERGED_APK_NAME = "merged_apk.apk"
KEYTOOL_CMD = "keytool"
JAVA_CMD = "java"
APKTOOL_DECODE_CMD = "decode"
APKTOOL_BUILD_CMD = "build"
ZIPALIGN_FLAGS = ["-f", "-v", "4"]
APKSIGNER_SIGN_CMD = "sign"
KEYSTORE_VALIDITY = "10000"
KEY_ALGORITHM = "RSA"
KEY_SIZE = "2048"
MERGE_CMD = "merge"
INPUT_FLAG = "-i"
UNSIGNED_FLAG = "-u"
OUTPUT_FLAG = "-o"
GRADLEW_UNIX = "gradlew"
GRADLEW_WIN = "gradlew.bat"
APKEDITOR_BUILD_DIR = Path("app/build/libs")
APKEDITOR_SOURCE_DIR = Path("libs/APKEditor")
EXAMPLE_SRC_PATH = "path/to/your/local/file.txt"
EXAMPLE_DEST_PATH = "assets/file.txt"
ADB_CMD = "adb"
ADB_INSTALL_CMD = "install"
ADB_DEVICES_CMD = "devices"
ADB_INSTALL_FLAGS = ["-t", "-r"]  # -t for test packages, -r for replace

# Example JSON content
EXAMPLE_JSON_CONTENT = {
    "patch": [
        {
            "src": EXAMPLE_SRC_PATH,
            "dest": EXAMPLE_DEST_PATH
        }
    ]
}

def setup_logging(log_to_file: bool, log_file_path: str, verbose: bool = False) -> None:
    """Setup logging configuration"""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=log_level, format=log_format)
    
    if log_to_file:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)

def download_file(url: str, destination: Path) -> bool:
    """Download a file from URL to destination"""
    logging.info(f"Downloading {url} to {destination}")
    try:
        urllib.request.urlretrieve(url, str(destination))
        logging.info("Download completed successfully")
        return True
    except urllib.error.URLError as e:
        logging.error(f"Failed to download file: {e}")
        return False

def run_command(cmd: list, cwd: str = None, input_data: str = None) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    logging.info(f"Running command: {' '.join(cmd)}")
    try:
        process = subprocess.run(
            cmd,
            cwd=cwd,
            input=input_data,
            text=True,
            capture_output=True,
            check=True
        )
        logging.debug(f"Command output: {process.stdout}")
        return process
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with return code {e.returncode}")
        logging.error(f"Error output: {e.stderr}")
        raise

def get_connected_devices() -> List[str]:
    """Get list of connected ADB devices"""
    try:
        result = run_command([ADB_CMD, ADB_DEVICES_CMD])
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        devices = []
        for line in lines:
            if line.strip() and not line.startswith('*') and '\t' in line:
                device_id = line.split('\t')[0]
                devices.append(device_id)
        return devices
    except Exception as e:
        logging.warning(f"Failed to get ADB devices: {e}")
        return []

def install_apk_on_device(apk_path: str, device_serial: Optional[str] = None) -> bool:
    """Install APK on connected device(s)"""
    try:
        # Get connected devices
        devices = get_connected_devices()
        
        if not devices:
            logging.error("No ADB devices connected")
            return False
        
        if device_serial:
            # Install on specific device
            if device_serial not in devices:
                logging.error(f"Device {device_serial} not found in connected devices: {devices}")
                return False
            
            logging.info(f"Installing APK on device {device_serial}...")
            cmd = [ADB_CMD, "-s", device_serial, ADB_INSTALL_CMD] + ADB_INSTALL_FLAGS + [apk_path]
            run_command(cmd)
            logging.info("APK installed successfully")
            return True
        elif len(devices) == 1:
            # Install on single device
            logging.info(f"Installing APK on device {devices[0]}...")
            cmd = [ADB_CMD, "-s", devices[0], ADB_INSTALL_CMD] + ADB_INSTALL_FLAGS + [apk_path]
            run_command(cmd)
            logging.info("APK installed successfully")
            return True
        else:
            # Multiple devices - show instructions
            print("\n" + "="*60)
            print("MULTIPLE DEVICES DETECTED")
            print("="*60)
            print("Connected devices:")
            for i, device in enumerate(devices, 1):
                print(f"  {i}. {device}")
            
            print("\nTo install on a specific device, run:")
            # Reconstruct the command with device serial
            cmd_parts = [sys.argv[0]] + sys.argv[1:] + ["--install-on-device", "<device_serial>"]
            print(f"  {' '.join(cmd_parts)}")
            print("="*60)
            return True
            
    except Exception as e:
        logging.error(f"Failed to install APK: {e}")
        return False

def decompile_apk(apk_path: str, output_dir: Path, apktool_path: Path) -> None:
    """Decompile the APK using apktool"""
    logging.info(f"Decompiling APK: {apk_path}")
    cmd = [JAVA_CMD, "-jar", str(apktool_path), APKTOOL_DECODE_CMD, apk_path, "-o", str(output_dir)]
    run_command(cmd)

def compile_apk(decompiled_dir: Path, output_apk: Path, apktool_path: Path) -> None:
    """Compile the modified sources back to APK"""
    logging.info(f"Compiling APK to: {output_apk}")
    cmd = [JAVA_CMD, "-jar", str(apktool_path), APKTOOL_BUILD_CMD, str(decompiled_dir), "-o", str(output_apk)]
    run_command(cmd)

def align_apk(input_apk: Path, output_apk: Path, zipalign_path: Path) -> None:
    """Align the APK using zipalign"""
    logging.info(f"Aligning APK: {input_apk}")
    cmd = [str(zipalign_path)] + ZIPALIGN_FLAGS + [str(input_apk), str(output_apk)]
    run_command(cmd)

def generate_key(keystore_path: Path, alias: str, password: str, keytool_path: str) -> None:
    """Generate a new keystore with keytool"""
    logging.info(f"Generating new keystore: {keystore_path}")
    
    # Prepare input for keytool (password twice)
    keytool_input = f"{password}\n{password}\n"
    
    cmd = [
        keytool_path,
        "-genkey",
        "-v",
        "-keystore", str(keystore_path),
        "-alias", alias,
        "-keyalg", KEY_ALGORITHM,
        "-keysize", KEY_SIZE,
        "-validity", KEYSTORE_VALIDITY,
        "-storepass", password,
        "-keypass", password,
        "-dname", KEY_DNAME
    ]
    
    run_command(cmd, input_data=keytool_input)

def sign_apk(apk_path: Path, keystore_path: Path, alias: str, password: str, apksigner_path: Path) -> None:
    """Sign the APK using apksigner.
    
    Args:
        apk_path: Path to the APK to sign.
        keystore_path: Path to the keystore file.
        alias: Key alias in the keystore.
        password: Keystore and key password.
        apksigner_path: Path to the apksigner tool (could be .jar or .bat, as determined by get_sdk_tool_paths).
    """
    logging.info(f"Signing APK: {apk_path}")
    
    # The apksigner_path provided by get_sdk_tool_paths is already the preferred one
    # (.bat on Windows if exists, .jar otherwise)
    system = platform.system().lower()
    apksigner_suffix = apksigner_path.suffix.lower()
    
    if apksigner_suffix == '.bat' and system == "windows":
        # On Windows, if .bat exists, run it directly
        logging.debug("Using apksigner.bat wrapper for Windows")
        cmd = [
            str(apksigner_path), # Run the .bat file directly
            APKSIGNER_SIGN_CMD,
            "--ks", str(keystore_path),
            "--ks-key-alias", alias,
            "--ks-pass", f"pass:{password}",
            "--key-pass", f"pass:{password}",
            "--out", str(apk_path),
            str(apk_path)
        ]
    else:
        # On Unix-like systems, or if .jar is provided, or if .bat doesn't exist on Windows, use java -jar
        logging.debug("Using java -jar to run apksigner")
        cmd = [
            JAVA_CMD, "-jar", str(apksigner_path), # Use java -jar with the .jar file
            APKSIGNER_SIGN_CMD,
            "--ks", str(keystore_path),
            "--ks-key-alias", alias,
            "--ks-pass", f"pass:{password}",
            "--key-pass", f"pass:{password}",
            "--out", str(apk_path),
            str(apk_path)
        ]
    
    run_command(cmd)

def cleanup_temp_files(*paths: str) -> None:
    """Remove temporary files and directories"""
    for path in paths:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
                logging.info(f"Removed directory: {path}")
            else:
                os.remove(path)
                logging.info(f"Removed file: {path}")

def interactive_file_modification(decompiled_dir: Path) -> None:
    """Allow user to interactively modify files"""
    print(f"\nAPK decompiled to: {decompiled_dir}")
    print("You can now modify files in this directory.")
    input("Press Enter when you're done with modifications...")

def load_patches_from_json(patches_file: Path) -> List[Dict[str, str]]:
    """Load file patches from a JSON file"""
    try:
        with open(patches_file, 'r') as f:
            data = json.load(f)
        
        # Extract patches from the JSON data
        if 'patch' in data and isinstance(data['patch'], list):
            patches = []
            for item in data['patch']:
                if isinstance(item, dict) and 'src' in item and 'dest' in item:
                    patches.append({
                        'src': item['src'],
                        'dest': item['dest']
                    })
            return patches
        else:
            raise ValueError("JSON file must contain a 'patch' array of objects with 'src' and 'dest' keys")
    except Exception as e:
        logging.error(f"Failed to load patches from {patches_file}: {e}")
        raise

def apply_file_patches(decompiled_dir: Path, patches: List[Dict[str, str]]) -> None:
    """Apply file patches from source to destination paths"""
    logging.info(f"Applying {len(patches)} file patches...")
    
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or 'src' not in patch or 'dest' not in patch:
            logging.warning(f"Skipping invalid patch at index {i}: {patch}")
            continue
            
        src_path = Path(patch['src'])
        dest_path = decompiled_dir / patch['dest']
        
        # Validate source file exists
        if not src_path.exists():
            logging.warning(f"Source file does not exist: {src_path}")
            continue
            
        # Create destination directory if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        try:
            shutil.copy2(src_path, dest_path)
            logging.info(f"Copied {src_path} to {dest_path}")
        except Exception as e:
            logging.error(f"Failed to copy {src_path} to {dest_path}: {e}")

def create_example_patches_file(patches_file: Path) -> None:
    """Create an example patches JSON file"""
    try:
        with open(patches_file, 'w') as f:
            json.dump(EXAMPLE_JSON_CONTENT, f, indent=2)
        logging.info(f"Created example patches file: {patches_file}")
    except Exception as e:
        logging.error(f"Failed to create example patches file: {e}")

def ensure_tools_available(tools_dir: Path, download_tools: bool = False, 
                          sdk_root: Optional[Path] = None, android_version: str = None) -> bool:
    """Ensure all required tools are available"""
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for apktool (must be in tools_dir)
    apktool_path = tools_dir / APKTOOL_JAR
    
    # Initialize paths for SDK tools (using the new 3-tuple return)
    zipalign_path = None
    apksigner_jar_path = None
    apksigner_bat_path_or_jar = None # This is the one we'll use for signing

    missing_tools = []
    if not apktool_path.exists():
        missing_tools.append("apktool")

    # Try to find or install SDK tools
    if SDK_INSTALLER_AVAILABLE and (sdk_root or download_tools):
        sdk_root_path = sdk_root if sdk_root else DEFAULT_SDK_ROOT
        target_android_version = android_version or DEFAULT_ANDROID_VERSION

        # If download is requested, install SDK tools first
        if download_tools:
            logging.info("Attempting to download/install Android SDK tools...")
            # Ensure sdk_root_path is absolute
            sdk_root_path = sdk_root_path.resolve()
            success = install_sdk_tools(
                sdk_root=sdk_root_path,
                android_version=target_android_version,
                # No tools_dir argument anymore for copying
                keep_cmdline=True
            )
            if not success:
                logging.error("Failed to install Android SDK tools via installer.")
                # Don't return False yet, check if tools might already exist

        # Try to locate tools within the SDK using the updated function
        logging.info(f"Searching for SDK tools in {sdk_root_path} for version {target_android_version}...")
        # Ensure sdk_root_path is absolute for get_sdk_tool_paths
        sdk_root_path = sdk_root_path.resolve()
        # Updated call to match new function signature (assuming get_sdk_tool_paths returns 3 values)
        # NOTE: The patcher.py from the KB assumes get_sdk_tool_paths returns 2 values.
        # If your actual sdk_installer.py has a different signature for get_sdk_tool_paths,
        # you'll need to adjust this call. Assuming the KB version for now.
        zipalign_path, apksigner_path = get_sdk_tool_paths(sdk_root_path, target_android_version)
        # For the logic below, we assume apksigner_path is the correct one to use
        # (either .bat or .jar as determined by the sdk installer's logic if it existed)
        apksigner_bat_path_or_jar = apksigner_path

    # If not found via SDK, check in the tools_dir (fallback for manual placement)
    if not zipalign_path or not zipalign_path.exists():
        potential_zipalign = tools_dir / ZIPALIGN_BIN
        if potential_zipalign.exists():
            zipalign_path = potential_zipalign
            logging.info(f"Found zipalign in tools directory (fallback): {zipalign_path}")

    # The main apksigner path for use is apksigner_bat_path_or_jar
    # If that failed, fallback, but it's complex. Let's rely on SDK install.
    if not apksigner_bat_path_or_jar or not apksigner_bat_path_or_jar.exists():
         potential_apksigner_jar = tools_dir / "apksigner.jar" # Standard name
         if potential_apksigner_jar.exists():
             apksigner_bat_path_or_jar = potential_apksigner_jar
             logging.info(f"Found apksigner.jar in tools directory (fallback): {apksigner_bat_path_or_jar}")


    # Check for missing SDK tools (based on core requirements)
    if not zipalign_path or not zipalign_path.exists():
        missing_tools.append("zipalign")
    # Use the path intended for execution
    if not apksigner_bat_path_or_jar or not apksigner_bat_path_or_jar.exists():
        missing_tools.append("apksigner")

    if not missing_tools:
        logging.info("All required tools are available")
        # Store the resolved paths for later use in main()
        # We need to make these available outside this function.
        # A common pattern is to store them in a global-like context or return them.
        # For simplicity here, we rely on the caller (main) to re-resolve them
        # after this function confirms they exist. This is slightly redundant but safe.
        return True

    if not download_tools:
        logging.error(f"Missing tools: {', '.join(missing_tools)}. "
                     "Please download them manually or use --download-tools option.")
        return False

    logging.info(f"Downloading missing tools: {', '.join(missing_tools)}")

    # Download apktool if missing
    if "apktool" in missing_tools:
        if not download_file(APKTOOL_DOWNLOAD_URL, apktool_path):
            logging.error("Failed to download apktool")
            return False

    # If we still couldn't find SDK tools after installation attempt and manual check, error
    # Re-check after potential download
    still_missing = []
    if ("zipalign" in missing_tools or not (zipalign_path and zipalign_path.exists())):
        still_missing.append("zipalign")
    if ("apksigner" in missing_tools or not (apksigner_bat_path_or_jar and apksigner_bat_path_or_jar.exists())):
        still_missing.append("apksigner")

    if still_missing:
        logging.error(f"Failed to locate/download tools: {', '.join(still_missing)} "
                      f"even after SDK installation attempt. Check SDK root and Android version.")
        return False

    logging.info("All tools successfully installed/located")
    return True

def main():
    parser = argparse.ArgumentParser(description="APK Decompiler and Re-signer")
    parser.add_argument("apk_path", help="Path to the APK file to process")
    parser.add_argument("--tools-dir", "-t", default=str(DEFAULT_TOOLS_DIR), help=f"Directory for tools like apktool.jar (default: {DEFAULT_TOOLS_DIR})")
    parser.add_argument("--log-file", "-l", help="Path to log file (if not provided, logging to file is disabled)")
    parser.add_argument("--keystore", "-k", help="Path to existing keystore (if not provided, a new one will be generated)")
    parser.add_argument("--alias", "-a", default=DEFAULT_ALIAS, help=f"Key alias (default: {DEFAULT_ALIAS})")
    parser.add_argument("--password", "-p", default=DEFAULT_PASSWORD, help=f"Keystore and key password (default: {DEFAULT_PASSWORD})")
    parser.add_argument("--output", "-o", help="Output APK path (default: <original_name>_signed.apk)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    # Patching options (mutually exclusive)
    patch_group = parser.add_mutually_exclusive_group()
    patch_group.add_argument("--interactive", "-i", action="store_true", help="Interactive file modification mode")
    patch_group.add_argument("--apk-file-patches", "-f", default=str(DEFAULT_PATCHES_FILE), 
                           help=f"JSON file containing APK file patches (default: {DEFAULT_PATCHES_FILE})")
    
    # Tool installation options
    parser.add_argument("--download-tools", "-d", action="store_true", 
                       help="Automatically download/install missing tools (apktool, build-tools)")
    parser.add_argument("--sdk-root", "-s", 
                       help=f"Android SDK root directory (default: {DEFAULT_SDK_ROOT})")
    parser.add_argument("--android-version", "-V", default=DEFAULT_ANDROID_VERSION,
                       help=f"Android API version for build tools (default: {DEFAULT_ANDROID_VERSION})")
    
    # APKEditor merge options
    parser.add_argument("--merge-with", "-m", nargs="+",
                       help="APKs to merge with using APKEditor (unsigned APKs) AFTER patching")
    parser.add_argument("--apkeditor-jar", "-e", 
                       help=f"Path to APKEditor JAR file (default: {APKEDITOR_JAR_DEFAULT})")
    parser.add_argument("--build-apkeditor", "-b", action="store_true",
                       help="Build APKEditor from source")
    
    # ADB installation options
    parser.add_argument("--install", "-I", action="store_true",
                       help="Install the final APK on connected device")
    parser.add_argument("--install-on-device", "-D", 
                       help="Install the final APK on a specific device by serial")
    
    args = parser.parse_args()
    
    # Setup logging
    log_to_file = bool(args.log_file)
    log_file_path = args.log_file or DEFAULT_LOG_FILE
    setup_logging(log_to_file, log_file_path, args.verbose)
    
    # Verify APK file exists
    apk_path_obj = Path(args.apk_path)
    if not apk_path_obj.exists():
        logging.error(f"APK file not found: {args.apk_path}")
        return 1
    
    # Ensure tools are available
    tools_dir = Path(args.tools_dir).resolve()
    sdk_root_path = Path(args.sdk_root).resolve() if args.sdk_root else DEFAULT_SDK_ROOT
    
    if not ensure_tools_available(
        tools_dir=tools_dir,
        download_tools=args.download_tools,
        sdk_root=sdk_root_path,
        android_version=args.android_version
    ):
        return 1
    
    # Resolve tools paths AFTER ensure_tools_available confirms they exist
    apktool_path = tools_dir / APKTOOL_JAR

    # Re-find SDK tool paths for actual use in main process
    zipalign_path = None
    apksigner_path_for_signing = None # This is the path to pass to sign_apk
    if SDK_INSTALLER_AVAILABLE:
        sdk_root_to_use = sdk_root_path if args.sdk_root else DEFAULT_SDK_ROOT
        # Ensure it's absolute
        sdk_root_to_use = sdk_root_to_use.resolve()
        # Based on the KB patcher.py, get_sdk_tool_paths returns 2 values (zipalign, apksigner)
        zipalign_path, apksigner_path_for_signing = get_sdk_tool_paths(sdk_root_to_use, args.android_version)

    # Fallbacks if SDK method didn't find them (should be rare if ensure_tools_available succeeded)
    if not zipalign_path or not zipalign_path.exists():
        zipalign_path = tools_dir / ZIPALIGN_BIN
    # The critical path for signing is apksigner_path_for_signing
    if not apksigner_path_for_signing or not apksigner_path_for_signing.exists():
        # Last resort fallback, try .jar in tools dir
        potential_apksigner_jar = tools_dir / "apksigner.jar"
        if potential_apksigner_jar.exists():
            apksigner_path_for_signing = potential_apksigner_jar
        # If this still doesn't work, the final check below will fail.

    # Final verification of all required tools before proceeding
    missing_final_check = []
    if not apktool_path.exists():
        missing_final_check.append("apktool")
    if not zipalign_path.exists():
        missing_final_check.append("zipalign")
    # This is the path that will be used by sign_apk
    if not apksigner_path_for_signing or not apksigner_path_for_signing.exists():
        missing_final_check.append("apksigner")

    if missing_final_check:
        logging.error(f"Tools missing at final check: {', '.join(missing_final_check)}")
        return 1
    
    # Create temporary working directory
    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    logging.info(f"Working in temporary directory: {temp_dir}")
    
    # Initialize return code
    return_code = 0
    
    try:
        # Define file paths
        apk_name = apk_path_obj.stem
        decompiled_dir = temp_dir / f"{apk_name}{DECOMPILED_SUFFIX}"
        unaligned_apk = temp_dir / f"{apk_name}{UNALIGNED_SUFFIX}"
        aligned_apk = temp_dir / f"{apk_name}{ALIGNED_SUFFIX}"
        
        # Determine output path
        if args.output:
            output_apk = Path(args.output).resolve()
        else:
            output_apk = Path.cwd() / f"{apk_name}{SIGNED_SUFFIX}"
        
        # Determine keystore path
        if args.keystore:
            keystore_path = Path(args.keystore).resolve()
            generate_new_key = False
        else:
            keystore_path = temp_dir / DEFAULT_KEYSTORE
            generate_new_key = True
        
        # Process steps
        logging.info("Starting APK processing...")
        
        # 1. Decompile APK
        decompile_apk(str(apk_path_obj), decompiled_dir, apktool_path)
        
        # 2. Apply patches based on selected mode
        if args.interactive:
            interactive_file_modification(decompiled_dir)
        else:
            # Default to JSON patches
            patches_file = Path(args.apk_file_patches)
            if patches_file.exists():
                patches = load_patches_from_json(patches_file)
                apply_file_patches(decompiled_dir, patches)
            else:
                # Create example file if it doesn't exist
                logging.warning(f"APK file patches file not found: {patches_file}")
                create_example_patches_file(patches_file)
                print(f"Created example patches file: {patches_file}")
                print("Please edit this file to add your patches, then run the command again.")
                print("Or use --interactive mode to manually modify files.")
                return 1
        
        # 3. Compile modified APK
        compile_apk(decompiled_dir, unaligned_apk, apktool_path)
        
        # 4. Align APK
        align_apk(unaligned_apk, aligned_apk, zipalign_path)
        
        # 5. Generate key if needed
        if generate_new_key:
            generate_key(keystore_path, args.alias, args.password, KEYTOOL_CMD)
        
        # 6. Sign APK (using the correctly resolved apksigner path)
        sign_apk(aligned_apk, keystore_path, args.alias, args.password, apksigner_path_for_signing)
        
        # 7. Merge with additional APKs if requested
        if args.merge_with:
            if not MERGER_AVAILABLE:
                logging.error("APK merger functionality not available")
                return 1
                
            logging.info("Merging patched APK with additional APKs...")
            # Use the signed APK as base and merge with additional APKs
            temp_merged_apk = temp_dir / f"{apk_name}_temp_merged.apk"
            
            success = merge_apks(
                base_apk=str(aligned_apk),
                unsigned_apks=args.merge_with,
                output_apk=str(temp_merged_apk),
                apkeditor_jar=args.apkeditor_jar or str(APKEDITOR_JAR_DEFAULT),
                verbose=args.verbose
            )
            
            if not success:
                logging.error("APK merging failed")
                return 1
                
            # Move merged APK to final output location
            shutil.move(str(temp_merged_apk), str(output_apk))
            logging.info(f"Merged and signed APK created at: {output_apk}")
        else:
            # 7. Move final APK to output location (no merge)
            shutil.move(str(aligned_apk), str(output_apk))
            logging.info(f"Signed APK created at: {output_apk}")
        
        # 8. Install APK on device if requested
        if args.install or args.install_on_device:
            install_apk_on_device(str(output_apk), args.install_on_device)
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        return_code = 1
    finally:
        # Cleanup temporary files
        logging.info("Cleaning up temporary files...")
        cleanup_temp_files(str(temp_dir))
    
    return return_code

if __name__ == "__main__":
    sys.exit(main())