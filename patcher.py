import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any
import urllib.request
import urllib.error

# Import our SDK installer
try:
    from sdk_installer import install_sdk_tools, setup_logging as setup_sdk_logging
    SDK_INSTALLER_AVAILABLE = True
except ImportError:
    SDK_INSTALLER_AVAILABLE = False
    def install_sdk_tools(*args, **kwargs):
        return False

# Constants
DEFAULT_TOOLS_DIR = "./tools"
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
DEFAULT_PATCHES_FILE = "apk_file_patches.json"
APKTOOL_DOWNLOAD_URL = "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.9.3.jar"

# Example JSON content
EXAMPLE_JSON_CONTENT = {
    "patch": [
        {
            "src": "path/to/your/local/file.txt",
            "dest": "assets/file.txt"
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

def decompile_apk(apk_path: str, output_dir: str, apktool_path: str) -> None:
    """Decompile the APK using apktool"""
    logging.info(f"Decompiling APK: {apk_path}")
    cmd = ["java", "-jar", apktool_path, "decode", apk_path, "-o", output_dir]
    run_command(cmd)

def compile_apk(decompiled_dir: str, output_apk: str, apktool_path: str) -> None:
    """Compile the modified sources back to APK"""
    logging.info(f"Compiling APK to: {output_apk}")
    cmd = ["java", "-jar", apktool_path, "build", decompiled_dir, "-o", output_apk]
    run_command(cmd)

def align_apk(input_apk: str, output_apk: str, zipalign_path: str) -> None:
    """Align the APK using zipalign"""
    logging.info(f"Aligning APK: {input_apk}")
    cmd = [zipalign_path, "-f", "-v", "4", input_apk, output_apk]
    run_command(cmd)

def generate_key(keystore_path: str, alias: str, password: str, keytool_path: str) -> None:
    """Generate a new keystore with keytool"""
    logging.info(f"Generating new keystore: {keystore_path}")
    
    # Prepare input for keytool (password twice)
    keytool_input = f"{password}\n{password}\n"
    
    cmd = [
        keytool_path,
        "-genkey",
        "-v",
        "-keystore", keystore_path,
        "-alias", alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", password,
        "-keypass", password,
        "-dname", KEY_DNAME
    ]
    
    run_command(cmd, input_data=keytool_input)

def sign_apk(apk_path: str, keystore_path: str, alias: str, password: str, apksigner_path: str) -> None:
    """Sign the APK using apksigner"""
    logging.info(f"Signing APK: {apk_path}")
    cmd = [
        "java", "-jar", apksigner_path,
        "sign",
        "--ks", keystore_path,
        "--ks-key-alias", alias,
        "--ks-pass", f"pass:{password}",
        "--key-pass", f"pass:{password}",
        "--out", apk_path,
        apk_path
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

def interactive_file_modification(decompiled_dir: str) -> None:
    """Allow user to interactively modify files"""
    print(f"\nAPK decompiled to: {decompiled_dir}")
    print("You can now modify files in this directory.")
    input("Press Enter when you're done with modifications...")

def load_patches_from_json(patches_file: str) -> List[Dict[str, str]]:
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

def apply_file_patches(decompiled_dir: str, patches: List[Dict[str, str]]) -> None:
    """Apply file patches from source to destination paths"""
    logging.info(f"Applying {len(patches)} file patches...")
    
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or 'src' not in patch or 'dest' not in patch:
            logging.warning(f"Skipping invalid patch at index {i}: {patch}")
            continue
            
        src_path = Path(patch['src'])
        dest_path = Path(decompiled_dir) / patch['dest']
        
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

def create_example_patches_file(patches_file: str) -> None:
    """Create an example patches JSON file"""
    try:
        with open(patches_file, 'w') as f:
            json.dump(EXAMPLE_JSON_CONTENT, f, indent=2)
        logging.info(f"Created example patches file: {patches_file}")
    except Exception as e:
        logging.error(f"Failed to create example patches file: {e}")

def ensure_tools_available(tools_dir: Path, download_tools: bool = False, 
                          sdk_root: str = None, android_version: str = None) -> bool:
    """Ensure all required tools are available"""
    tools_dir.mkdir(parents=True, exist_ok=True)
    
    # Check for required tools
    apktool_path = tools_dir / APKTOOL_JAR
    apksigner_path = tools_dir / APKSIGNER_JAR
    zipalign_path = tools_dir / ZIPALIGN_BIN
    
    missing_tools = []
    if not apktool_path.exists():
        missing_tools.append("apktool")
    if not apksigner_path.exists():
        missing_tools.append("apksigner")
    if not zipalign_path.exists():
        missing_tools.append("zipalign")
    
    if not missing_tools:
        logging.info("All required tools are available")
        return True
    
    if not download_tools:
        logging.error(f"Missing tools: {', '.join(missing_tools)}. "
                     "Please download them manually or use --download-tools option.")
        return False
    
    logging.info(f"Downloading missing tools: {', '.join(missing_tools)}")
    
    # Download apktool
    if "apktool" in missing_tools:
        if not download_file(APKTOOL_DOWNLOAD_URL, apktool_path):
            logging.error("Failed to download apktool")
            return False
    
    # Install Android SDK tools if needed
    if "apksigner" in missing_tools or "zipalign" in missing_tools:
        if not SDK_INSTALLER_AVAILABLE:
            logging.error("SDK installer not available. Please install Android SDK tools manually.")
            return False
        
        # Setup SDK logging
        setup_sdk_logging()
        
        # Install SDK tools
        sdk_root_path = Path(sdk_root) if sdk_root else Path.home() / "android-sdk"
        success = install_sdk_tools(
            sdk_root=sdk_root_path,
            android_version=android_version or "34",  # Default to Android 14
            tools_dir=tools_dir,
            keep_cmdline=True
        )
        
        if not success:
            logging.error("Failed to install Android SDK tools")
            return False
    
    # Verify tools are now available
    if (apktool_path.exists() and 
        apksigner_path.exists() and 
        zipalign_path.exists()):
        logging.info("All tools successfully installed")
        return True
    else:
        missing = []
        if not apktool_path.exists():
            missing.append("apktool")
        if not apksigner_path.exists():
            missing.append("apksigner")
        if not zipalign_path.exists():
            missing.append("zipalign")
        logging.error(f"Failed to install tools: {', '.join(missing)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="APK Decompiler and Re-signer")
    parser.add_argument("apk_path", help="Path to the APK file to process")
    parser.add_argument("--tools-dir", default=DEFAULT_TOOLS_DIR, help=f"Directory containing tools (default: {DEFAULT_TOOLS_DIR})")
    parser.add_argument("--log-file", help="Path to log file (if not provided, logging to file is disabled)")
    parser.add_argument("--keystore", help="Path to existing keystore (if not provided, a new one will be generated)")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help=f"Key alias (default: {DEFAULT_ALIAS})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help=f"Keystore and key password (default: {DEFAULT_PASSWORD})")
    parser.add_argument("--output", help="Output APK path (default: <original_name>_signed.apk)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    # Patching options (mutually exclusive)
    patch_group = parser.add_mutually_exclusive_group()
    patch_group.add_argument("--interactive", action="store_true", help="Interactive file modification mode")
    patch_group.add_argument("--apk-file-patches", default=DEFAULT_PATCHES_FILE, 
                           help=f"JSON file containing APK file patches (default: {DEFAULT_PATCHES_FILE})")
    
    # Tool installation options
    parser.add_argument("--download-tools", action="store_true", 
                       help="Automatically download missing tools")
    parser.add_argument("--sdk-root", 
                       help="Android SDK root directory for tool installation")
    parser.add_argument("--android-version", default="34",
                       help="Android API version for build tools (default: 34)")
    
    args = parser.parse_args()
    
    # Setup logging
    log_to_file = bool(args.log_file)
    log_file_path = args.log_file or DEFAULT_LOG_FILE
    setup_logging(log_to_file, log_file_path, args.verbose)
    
    # Verify APK file exists
    if not os.path.isfile(args.apk_path):
        logging.error(f"APK file not found: {args.apk_path}")
        return 1
    
    # Ensure tools are available
    tools_dir = Path(args.tools_dir).resolve()
    if not ensure_tools_available(
        tools_dir=tools_dir,
        download_tools=args.download_tools,
        sdk_root=args.sdk_root,
        android_version=args.android_version
    ):
        return 1
    
    # Resolve tools paths
    apktool_path = tools_dir / APKTOOL_JAR
    apksigner_path = tools_dir / APKSIGNER_JAR
    zipalign_path = tools_dir / ZIPALIGN_BIN
    
    # Verify all tools exist
    for tool in [apktool_path, apksigner_path, zipalign_path]:
        if not tool.exists():
            logging.error(f"Required tool not found: {tool}")
            return 1
    
    # Create temporary working directory
    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    logging.info(f"Working in temporary directory: {temp_dir}")
    
    # Initialize return code
    return_code = 0
    
    try:
        # Define file paths
        apk_name = Path(args.apk_path).stem
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
        decompile_apk(str(args.apk_path), str(decompiled_dir), str(apktool_path))
        
        # 2. Apply patches based on selected mode
        if args.interactive:
            interactive_file_modification(str(decompiled_dir))
        else:
            # Default to JSON patches
            if os.path.exists(args.apk_file_patches):
                patches = load_patches_from_json(args.apk_file_patches)
                apply_file_patches(str(decompiled_dir), patches)
            else:
                # Create example file if it doesn't exist
                logging.warning(f"APK file patches file not found: {args.apk_file_patches}")
                create_example_patches_file(args.apk_file_patches)
                print(f"Created example patches file: {args.apk_file_patches}")
                print("Please edit this file to add your patches, then run the command again.")
                print("Or use --interactive mode to manually modify files.")
                return 1
        
        # 3. Compile modified APK
        compile_apk(str(decompiled_dir), str(unaligned_apk), str(apktool_path))
        
        # 4. Align APK
        align_apk(str(unaligned_apk), str(aligned_apk), str(zipalign_path))
        
        # 5. Generate key if needed
        if generate_new_key:
            generate_key(str(keystore_path), args.alias, args.password, "keytool")
        
        # 6. Sign APK
        sign_apk(str(aligned_apk), str(keystore_path), args.alias, args.password, str(apksigner_path))
        
        # 7. Move final APK to output location
        shutil.move(str(aligned_apk), str(output_apk))
        logging.info(f"Signed APK created at: {output_apk}")
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        return_code = 1
    finally:
        # Cleanup temporary files
        logging.info("Cleaning up temporary files...")
        cleanup_temp_files(str(temp_dir))
    
    return return_code

if __name__ == "__main__":
    sys.exit(main())}

def setup_logging(log_to_file: bool, log_file_path: str) -> None:
    """Setup logging configuration"""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)
    
    if log_to_file:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)

def run_command(cmd: list, cwd: str = None, input_ str = None) -> subprocess.CompletedProcess:
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

def decompile_apk(apk_path: str, output_dir: str, apktool_path: str) -> None:
    """Decompile the APK using apktool"""
    logging.info(f"Decompiling APK: {apk_path}")
    cmd = ["java", "-jar", apktool_path, "decode", apk_path, "-o", output_dir]
    run_command(cmd)

def compile_apk(decompiled_dir: str, output_apk: str, apktool_path: str) -> None:
    """Compile the modified sources back to APK"""
    logging.info(f"Compiling APK to: {output_apk}")
    cmd = ["java", "-jar", apktool_path, "build", decompiled_dir, "-o", output_apk]
    run_command(cmd)

def align_apk(input_apk: str, output_apk: str, zipalign_path: str) -> None:
    """Align the APK using zipalign"""
    logging.info(f"Aligning APK: {input_apk}")
    cmd = [zipalign_path, "-f", "-v", "4", input_apk, output_apk]
    run_command(cmd)

def generate_key(keystore_path: str, alias: str, password: str, keytool_path: str) -> None:
    """Generate a new keystore with keytool"""
    logging.info(f"Generating new keystore: {keystore_path}")
    
    # Prepare input for keytool (password twice)
    keytool_input = f"{password}\n{password}\n"
    
    cmd = [
        keytool_path,
        "-genkey",
        "-v",
        "-keystore", keystore_path,
        "-alias", alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", password,
        "-keypass", password,
        "-dname", KEY_DNAME
    ]
    
    run_command(cmd, input_data=keytool_input)

def sign_apk(apk_path: str, keystore_path: str, alias: str, password: str, apksigner_path: str) -> None:
    """Sign the APK using apksigner"""
    logging.info(f"Signing APK: {apk_path}")
    cmd = [
        "java", "-jar", apksigner_path,
        "sign",
        "--ks", keystore_path,
        "--ks-key-alias", alias,
        "--ks-pass", f"pass:{password}",
        "--key-pass", f"pass:{password}",
        "--out", apk_path,
        apk_path
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

def interactive_file_modification(decompiled_dir: str) -> None:
    """Allow user to interactively modify files"""
    print(f"\nAPK decompiled to: {decompiled_dir}")
    print("You can now modify files in this directory.")
    input("Press Enter when you're done with modifications...")

def load_patches_from_json(patches_file: str) -> List[Dict[str, str]]:
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

def apply_file_patches(decompiled_dir: str, patches: List[Dict[str, str]]) -> None:
    """Apply file patches from source to destination paths"""
    logging.info(f"Applying {len(patches)} file patches...")
    
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or 'src' not in patch or 'dest' not in patch:
            logging.warning(f"Skipping invalid patch at index {i}: {patch}")
            continue
            
        src_path = Path(patch['src'])
        dest_path = Path(decompiled_dir) / patch['dest']
        
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

def create_example_patches_file(patches_file: str) -> None:
    """Create an example patches JSON file"""
    try:
        with open(patches_file, 'w') as f:
            json.dump(EXAMPLE_JSON_CONTENT, f, indent=2)
        logging.info(f"Created example patches file: {patches_file}")
    except Exception as e:
        logging.error(f"Failed to create example patches file: {e}")

def main():
    parser = argparse.ArgumentParser(description="APK Decompiler and Re-signer")
    parser.add_argument("apk_path", help="Path to the APK file to process")
    parser.add_argument("--tools-dir", default=DEFAULT_TOOLS_DIR, help=f"Directory containing tools (default: {DEFAULT_TOOLS_DIR})")
    parser.add_argument("--log-file", help="Path to log file (if not provided, logging to file is disabled)")
    parser.add_argument("--keystore", help="Path to existing keystore (if not provided, a new one will be generated)")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help=f"Key alias (default: {DEFAULT_ALIAS})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help=f"Keystore and key password (default: {DEFAULT_PASSWORD})")
    parser.add_argument("--output", help="Output APK path (default: <original_name>_signed.apk)")
    
    # Patching options (mutually exclusive)
    patch_group = parser.add_mutually_exclusive_group()
    patch_group.add_argument("--interactive", action="store_true", help="Interactive file modification mode")
    patch_group.add_argument("--apk-file-patches", default=DEFAULT_PATCHES_FILE, 
                           help=f"JSON file containing APK file patches (default: {DEFAULT_PATCHES_FILE})")
    
    args = parser.parse_args()
    
    # Setup logging
    log_to_file = bool(args.log_file)
    log_file_path = args.log_file or DEFAULT_LOG_FILE
    setup_logging(log_to_file, log_file_path)
    
    # Verify APK file exists
    if not os.path.isfile(args.apk_path):
        logging.error(f"APK file not found: {args.apk_path}")
        return 1
    
    # Resolve tools paths
    tools_dir = Path(args.tools_dir).resolve()
    apktool_path = tools_dir / APKTOOL_JAR
    apksigner_path = tools_dir / APKSIGNER_JAR
    zipalign_path = tools_dir / ZIPALIGN_BIN
    
    for tool in [apktool_path, apksigner_path, zipalign_path]:
        if not tool.exists():
            logging.error(f"Required tool not found: {tool}")
            return 1
    
    # Create temporary working directory
    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    logging.info(f"Working in temporary directory: {temp_dir}")
    
    # Initialize return code
    return_code = 0
    
    try:
        # Define file paths
        apk_name = Path(args.apk_path).stem
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
        decompile_apk(str(args.apk_path), str(decompiled_dir), str(apktool_path))
        
        # 2. Apply patches based on selected mode
        if args.interactive:
            interactive_file_modification(str(decompiled_dir))
        else:
            # Default to JSON patches
            if os.path.exists(args.apk_file_patches):
                patches = load_patches_from_json(args.apk_file_patches)
                apply_file_patches(str(decompiled_dir), patches)
            else:
                # Create example file if it doesn't exist
                logging.warning(f"APK file patches file not found: {args.apk_file_patches}")
                create_example_patches_file(args.apk_file_patches)
                print(f"Created example patches file: {args.apk_file_patches}")
                print("Please edit this file to add your patches, then run the command again.")
                print("Or use --interactive mode to manually modify files.")
                return 1
        
        # 3. Compile modified APK
        compile_apk(str(decompiled_dir), str(unaligned_apk), str(apktool_path))
        
        # 4. Align APK
        align_apk(str(unaligned_apk), str(aligned_apk), str(zipalign_path))
        
        # 5. Generate key if needed
        if generate_new_key:
            generate_key(str(keystore_path), args.alias, args.password, "keytool")
        
        # 6. Sign APK
        sign_apk(str(aligned_apk), str(keystore_path), args.alias, args.password, str(apksigner_path))
        
        # 7. Move final APK to output location
        shutil.move(str(aligned_apk), str(output_apk))
        logging.info(f"Signed APK created at: {output_apk}")
        
    except Exception as e:
        logging.error(f"Processing failed: {str(e)}")
        return_code = 1
    finally:
        # Cleanup temporary files
        logging.info("Cleaning up temporary files...")
        cleanup_temp_files(str(temp_dir))
    
    return return_code

if __name__ == "__main__":
    sys.exit(main())        raise

def apply_file_patches(decompiled_dir: str, patches: List[Dict[str, str]]) -> None:
    """Apply file patches from source to destination paths"""
    logging.info(f"Applying {len(patches)} file patches...")
    
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict) or 'src' not in patch or 'dest' not in patch:
            logging.warning(f"Skipping invalid patch at index {i}: {patch}")
            continue
            
        src_path = Path(patch['src'])
        dest_path = Path(decompiled_dir) / patch['dest']
        
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

def create_example_patches_file(patches_file: str) -> None:
    """Create an example patches JSON file"""
    try:
        with open(patches_file, 'w') as f:
            json.dump(EXAMPLE_JSON_CONTENT, f, indent=2)
        logging.info(f"Created example patches file: {patches_file}")
    except Exception as e:
        logging.error(f"Failed to create example patches file: {e}")

def main():
    parser = argparse.ArgumentParser(description="APK Decompiler and Re-signer")
    parser.add_argument("apk_path", help="Path to the APK file to process")
    parser.add_argument("--tools-dir", default=DEFAULT_TOOLS_DIR, help=f"Directory containing tools (default: {DEFAULT_TOOLS_DIR})")
    parser.add_argument("--log-file", help="Path to log file (if not provided, logging to file is disabled)")
    parser.add_argument("--keystore", help="Path to existing keystore (if not provided, a new one will be generated)")
    parser.add_argument("--alias", default=DEFAULT_ALIAS, help=f"Key alias (default: {DEFAULT_ALIAS})")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help=f"Keystore and key password (default: {DEFAULT_PASSWORD})")
    parser.add_argument("--output", help="Output APK path (default: <original_name>_signed.apk)")
    
    # Patching options (mutually exclusive)
    patch_group = parser.add_mutually_exclusive_group()
    patch_group.add_argument("--interactive", action="store_true", help="Interactive file modification mode")
    patch_group.add_argument("--apk-file-patches", default=DEFAULT_PATCHES_FILE, 
                           help=f"JSON file containing APK file patches (default: {DEFAULT_PATCHES_FILE})")
    
    args = parser.parse_args()
    
    # Setup logging
    log_to_file = bool(args.log_file)
    log_file_path = args.log_file or DEFAULT_LOG_FILE
    setup_logging(log_to_file, log_file_path)
    
    # Verify APK file exists
    if not os.path.isfile(args.apk_path):
        logging.error(f"APK file not found: {args.apk_path}")
        return 1
    
    # Resolve tools paths
    tools_dir = Path(args.tools_dir).resolve()
    apktool_path = tools_dir / APKTOOL_JAR
    apksigner_path = tools_dir / APKSIGNER_JAR
    zipalign_path = tools_dir / ZIPALIGN_BIN
    
    for tool in [apktool_path, apksigner_path, zipalign_path]:
        if not tool.exists():
            logging.error(f"Required tool not found: {tool}")
            return 1
    
    # Create temporary working directory
    temp_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    logging.info(f"Working in temporary directory: {temp_dir}")
    
    # Initialize return code
    return_code = 0
    
    try:
        # Define file paths
        apk_name = Path(args.apk_path).stem
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
        decompile_apk(str(args.apk_path), str(decompiled_dir), str(apktool_path))
        
        # 2. Apply patches based on selected mode
        if args.interactive:
            interactive_file_modification(str(decompiled_dir))
        else:
            # Default to JSON patches
            if os.path.exists(args.apk_file_patches):
                patches = load_patches_from_json(args.apk_file_patches)
                apply_file_patches(str(decompiled_dir), patches)
            else:
                # Create example file if it doesn't exist
                logging.warning(f"APK file patches file not found: {args.apk_file_patches}")
                create_example_patches_file(args.apk_file_patches)
                print(f"Created example patches file: {args.apk_file_patches}")
                print("Please edit this file to add your patches, then run the command again.")
                print("Or use --interactive mode to manually modify files.")
                return 1
        
        # 3. Compile modified APK
        compile_apk(str(decompiled_dir), str(unaligned_apk), str(apktool_path))
        
        # 4. Align APK
        align_apk(str(unaligned_apk), str(aligned_apk), str(zipalign_path))
        
        # 5. Generate key if needed
        if generate_new_key:
            generate_key(str(keystore_path), args.alias, args.password, "keytool")
        
        # 6. Sign APK
        sign_apk(str(aligned_apk), str(keystore_path), args.alias, args.password, str(apksigner_path))
        
        # 7. Move final APK to output location
        shutil.move(str(aligned_apk), str(output_apk))
        logging.info(f"Signed APK created at: {output_apk}")
        
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
