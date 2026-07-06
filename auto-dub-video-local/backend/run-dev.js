const fs = require('fs');
const { spawn } = require('child_process');
const path = require('path');

const isWin = process.platform === 'win32';
const venvUvicorn = isWin 
  ? path.join(__dirname, '.venv', 'Scripts', 'uvicorn.exe') 
  : path.join(__dirname, '.venv', 'bin', 'uvicorn');

let cmd = 'uvicorn';
let useVenv = false;
if (fs.existsSync(venvUvicorn)) {
  cmd = venvUvicorn;
  useVenv = true;
  console.log(`Using virtual environment uvicorn: ${cmd}`);
} else {
  console.log('Virtual environment uvicorn not found. Running with global uvicorn command...');
}

// On Windows, if we are running an absolute path to an executable .exe, we do not need shell: true.
// Disabling shell: true prevents Windows CMD from misinterpreting spaces in the folder path.
const shellOption = useVenv && isWin ? false : true;

const child = spawn(cmd, ['app.main:app', '--reload', '--port', '8000'], {
  stdio: 'inherit',
  shell: shellOption,
  cwd: __dirname
});

child.on('error', (err) => {
  console.error('Failed to start uvicorn:', err.message);
  console.log('\nMake sure Python and uvicorn are installed. If you are using a virtual environment, please run:');
  console.log('  python -m venv .venv');
  console.log('  ' + (isWin ? '.venv\\Scripts\\activate' : 'source .venv/bin/activate'));
  console.log('  pip install -r requirements.txt');
  process.exit(1);
});

child.on('exit', (code) => {
  process.exit(code || 0);
});
