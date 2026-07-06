const { spawn } = require('child_process');
const path = require('path');

console.log('Starting Backend and Frontend dev servers concurrently...\n');

// Start backend
const backend = spawn('npm', ['run', 'dev'], {
  stdio: 'inherit',
  shell: true,
  cwd: path.join(__dirname, 'backend')
});

// Start frontend
const frontend = spawn('npm', ['run', 'dev'], {
  stdio: 'inherit',
  shell: true,
  cwd: path.join(__dirname, 'frontend')
});

// Handle child exit to shut down other processes
const cleanUp = () => {
  console.log('\nStopping dev servers...');
  try {
    backend.kill('SIGINT');
  } catch (e) {}
  try {
    frontend.kill('SIGINT');
  } catch (e) {}
  process.exit(0);
};

backend.on('exit', (code) => {
  if (code !== null && code !== 0) {
    console.log(`Backend process exited with code ${code}`);
  }
  cleanUp();
});

frontend.on('exit', (code) => {
  if (code !== null && code !== 0) {
    console.log(`Frontend process exited with code ${code}`);
  }
  cleanUp();
});

process.on('SIGINT', cleanUp);
process.on('SIGTERM', cleanUp);
process.on('SIGHUP', cleanUp);
