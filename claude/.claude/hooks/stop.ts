#!/usr/bin/env tsx
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
import { platform } from 'os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Detect if running from global installation
const isGlobalInstall = __dirname.includes('.claude/hooks');
const logsDir = isGlobalInstall 
  ? join(process.env.HOME || process.cwd(), '.claude', 'logs')
  : join(__dirname, '../../logs');
  
if (!existsSync(logsDir)) {
  mkdirSync(logsDir, { recursive: true });
}

// Read input from stdin
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('readable', () => {
  let chunk;
  while ((chunk = process.stdin.read()) !== null) {
    input += chunk;
  }
});

process.stdin.on('end', async () => {
  try {
    const data = JSON.parse(input);
    
    // Log the stop event
    const logFile = join(logsDir, 'stop.json');
    let logs = [];
    if (existsSync(logFile)) {
      try {
        logs = JSON.parse(readFileSync(logFile, 'utf8'));
      } catch (e) {
        logs = [];
      }
    }
    
    logs.push({
      timestamp: new Date().toISOString(),
      ...data
    });
    
    writeFileSync(logFile, JSON.stringify(logs, null, 2));
    
    // Play completion sound or speak notification
    const os_platform = platform();
    
    // Define the callback for after notification
    const afterNotification = () => {
      // If --chat flag is present, process the transcript
      if (process.argv.includes('--chat') && data.transcript_path) {
        try {
          const transcriptPath = data.transcript_path;
          if (existsSync(transcriptPath)) {
            const transcriptContent = readFileSync(transcriptPath, 'utf8');
            const lines = transcriptContent.split('\n').filter(line => line.trim());
            const chatData = [];
            
            for (const line of lines) {
              try {
                chatData.push(JSON.parse(line));
              } catch (e) {
                // Skip invalid lines
              }
            }
            
            const chatLogFile = join(logsDir, 'chat.json');
            writeFileSync(chatLogFile, JSON.stringify(chatData, null, 2));
          }
        } catch (e) {
          console.error('Error processing transcript:', e);
        }
      }
      
      process.exit(0);
    };
    
    // Check if --speak flag is present and on macOS
    if (process.argv.includes('--speak') && os_platform === 'darwin') {
      const message = "Your agent has finished";
      const cmd = `say "${message}"`;
      
      exec(cmd, (err) => {
        if (err) {
          console.error('Error speaking notification:', err.message);
        }
        afterNotification();
      });
    } else {
      // Default behavior: play sound file
      let cmd: string;
      
      if (os_platform === 'darwin') {
        // Use macOS built-in system sound
        cmd = `afplay /System/Library/Sounds/Glass.aiff`;
        
        exec(cmd, (err) => {
          if (err) {
            console.error('Error playing sound:', err.message);
          }
          afterNotification();
        });
      } else {
        // For non-macOS platforms, try to use custom sound file
        const soundFile = isGlobalInstall
          ? join(process.env.HOME || process.cwd(), '.claude', 'on-agent-complete.wav')
          : join(__dirname, '../../on-agent-complete.wav');
        
        // Check if sound file exists
        if (existsSync(soundFile)) {
          // Determine the command based on the platform
          if (os_platform === 'win32') {
            cmd = `powershell -c "(New-Object Media.SoundPlayer '${soundFile}').PlaySync()"`;
          } else {
            // Linux - try multiple players
            cmd = `aplay "${soundFile}" 2>/dev/null || paplay "${soundFile}" 2>/dev/null || play "${soundFile}" 2>/dev/null`;
          }
          
          exec(cmd, (err) => {
            if (err) {
              console.error('Error playing sound:', err.message);
            }
            afterNotification();
          });
        } else {
          console.error(`Sound file not found: ${soundFile}`);
          console.error('Please ensure on-agent-complete.wav exists in the repository root');
          afterNotification();
        }
      }
    }
  } catch (error) {
    console.error('Error processing stop event:', error);
    process.exit(1);
  }
});