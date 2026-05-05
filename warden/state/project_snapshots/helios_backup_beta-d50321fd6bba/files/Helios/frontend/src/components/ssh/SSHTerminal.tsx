import React, { useEffect, useRef } from 'react';
import { Box } from '@chakra-ui/react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import { io, Socket } from 'socket.io-client';

import 'xterm/css/xterm.css';

interface SSHTerminalProps {
  connectionId: string;
}

const SSHTerminal: React.FC<SSHTerminalProps> = ({ connectionId }) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<Terminal | null>(null);
  const socketRef = useRef<Socket | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!terminalRef.current || !connectionId) return;

    // Initialize xterm.js
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#ffffff',
      },
    });

    // Initialize addons
    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();

    term.loadAddon(fitAddon);
    term.loadAddon(webLinksAddon);

    // Store refs
    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    // Open terminal in container
    term.open(terminalRef.current);
    fitAddon.fit();

    // Initialize socket connection
    const socket = io('/terminal', {
      path: '/api/socket.io',
      query: {
        connectionId,
      },
    });

    socketRef.current = socket;

    // Handle terminal data
    term.onData(data => {
      socket.emit('data', data);
    });

    // Handle incoming data
    socket.on('data', (data: string) => {
      term.write(data);
    });

    // Handle connection status
    socket.on('connect', () => {
      term.write('\r\nConnected to terminal\r\n');
    });

    socket.on('disconnect', () => {
      term.write('\r\nDisconnected from terminal\r\n');
    });

    socket.on('error', (error: string) => {
      term.write(`\r\nError: ${error}\r\n`);
    });

    // Handle window resize
    const handleResize = () => {
      if (fitAddonRef.current) {
        fitAddonRef.current.fit();
        const term = xtermRef.current!;
        socket.emit('resize', { 
          rows: term.rows,
          cols: term.cols 
        });
      }
    };

    window.addEventListener('resize', handleResize);

    // Initial fit
    handleResize();

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize);
      socket.disconnect();
      term.dispose();
    };
  }, [connectionId]);

  return (
    <Box
      ref={terminalRef}
      height="100%"
      width="100%"
      bg="gray.900"
      borderRadius="md"
      overflow="hidden"
    />
  );
};

export default SSHTerminal;
