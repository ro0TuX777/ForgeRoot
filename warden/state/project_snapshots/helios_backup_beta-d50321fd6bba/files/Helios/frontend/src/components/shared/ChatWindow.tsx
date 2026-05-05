import React, { useState, useEffect, useRef } from 'react';
import { Box, Flex, Text, Input, IconButton, VStack, Avatar, useColorModeValue, Button } from '@chakra-ui/react';
import { Send, Download } from 'lucide-react';
import { useUser } from '../../context/UserContext';
import getSocket from '../../utils/socket';

interface ChatMessage {
  id: string;
  sender: {
    id: string;
    username: string;
  };
  content: string;
  timestamp: string;
  team: string;
  sent_at?: string;
  delivered_at?: string;
}

const CHAT_HISTORY_LIMIT = 50;

const ChatWindow: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState('');
  const { username, id: userId, team } = useUser();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const bgColor = useColorModeValue('white', 'gray.800');
  const socket = getSocket();

  useEffect(() => {
    if (!socket || !userId || !team) return;

    // Join team chat room
    socket.emit('joinTeam', { team, userId });
    console.log(`Joining team ${team}`);

    // Listen for chat history
    socket.on('chatHistory', (history: ChatMessage[]) => {
      console.log('Received chat history:', history);
      const sortedMessages = history
        .sort((a: ChatMessage, b: ChatMessage) => 
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
        )
        .slice(-CHAT_HISTORY_LIMIT);
      setMessages(sortedMessages);
      scrollToBottom();
    });

    // Listen for new messages
    socket.on('chatMessage', (message: ChatMessage) => {
      console.log('Received new message:', message);
      setMessages(prevMessages => {
        const updatedMessages = [...prevMessages, message];
        return updatedMessages.slice(-CHAT_HISTORY_LIMIT);
      });
      scrollToBottom();
      
      // Send delivery confirmation
      socket.emit('messageDelivered', message.id);
    });

    return () => {
      socket.off('chatHistory');
      socket.off('chatMessage');
    };
  }, [socket, userId, team]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffInHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60);

    // If message is from today, show time only
    if (diffInHours < 24 && date.getDate() === now.getDate()) {
      return new Intl.DateTimeFormat('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      }).format(date);
    }

    // If message is from this week, show day and time
    if (diffInHours < 168) { // 7 days
      return new Intl.DateTimeFormat('en-US', {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      }).format(date);
    }

    // Otherwise show full date and time
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }).format(date);
  };

  const handleSendMessage = () => {
    if (!newMessage.trim() || !username || !userId || !team) return;

    const message = {
      id: Date.now().toString(),
      sender: {
        id: userId,
        username: username
      },
      content: newMessage.trim(),
      timestamp: new Date().toISOString(),
      team
    };

    console.log('Sending message:', message);
    socket.emit('sendMessage', message);
    setNewMessage('');
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const getBorderColor = () => {
    switch (team) {
      case 'red':
        return 'red.500';
      case 'blue':
        return 'blue.500';
      case 'white':
        return 'white.500';
      case 'observer':
        return 'yellow.500';
      default:
        return 'gray.200';
    }
  };

  return (
    <Box
      bg={bgColor}
      h="full"
      rounded="lg"
      shadow="md"
      display="flex"
      flexDirection="column"
      borderWidth="2px"
      borderColor={getBorderColor()}
    >
      <Flex p={4} borderBottom="1px" borderColor="gray.200" justify="space-between" align="center">
        <Text fontSize="lg" fontWeight="bold">
          Mission Chat
        </Text>
        <Button
          leftIcon={<Download size={16} />}
          size="sm"
          colorScheme={team === 'red' ? 'red' : team === 'blue' ? 'blue' : 'gray'}
          variant="outline"
          onClick={() => {
            // Format messages into text content
            const content = messages.map(msg => {
              const timestamp = new Date(msg.timestamp);
              const formattedTime = timestamp.toLocaleString('en-US', {
                month: '2-digit',
                day: '2-digit',
                year: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
              });
              return `[${formattedTime}] ${msg.sender.username}: ${msg.content}`;
            }).join('\n');

            // Create timestamp for filename
            const now = new Date();
            const fileTimestamp = `${
              (now.getMonth() + 1).toString().padStart(2, '0')
            }${
              now.getDate().toString().padStart(2, '0')
            }${
              now.getFullYear().toString().slice(-2)
            }${
              now.getHours().toString().padStart(2, '0')
            }${
              now.getMinutes().toString().padStart(2, '0')
            }`;

            // Create filename
            const filename = `ChatLog_${username}_${fileTimestamp}.txt`;

            // Create blob and trigger download
            const blob = new Blob([content], { type: 'text/plain' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
          }}
        >
          Export Chat
        </Button>
      </Flex>

      <VStack
        flex="1"
        overflowY="auto"
        p={4}
        spacing={4}
        align="stretch"
        css={{
          '&::-webkit-scrollbar': {
            width: '4px',
          },
          '&::-webkit-scrollbar-track': {
            width: '6px',
          },
          '&::-webkit-scrollbar-thumb': {
            background: 'gray.200',
            borderRadius: '24px',
          },
        }}
      >
        {messages.map((message) => (
          <Box key={message.id}>
            <Flex align="center" mb={1}>
              <Avatar size="xs" name={message.sender.username} mr={2} />
              <Text fontWeight="medium" fontSize="sm">
                {message.sender.username}
              </Text>
              <Flex align="center" ml={2}>
                <Text fontSize="xs" color="gray.500">
                  {formatTime(message.timestamp)}
                </Text>
                {message.delivered_at && (
                  <Text fontSize="xs" color="green.500" ml={1}>
                    ✓✓
                  </Text>
                )}
                {message.sent_at && !message.delivered_at && (
                  <Text fontSize="xs" color="gray.500" ml={1}>
                    ✓
                  </Text>
                )}
              </Flex>
            </Flex>
            <Text pl={8} fontSize="sm">
              {message.content}
            </Text>
          </Box>
        ))}
        <div ref={messagesEndRef} />
      </VStack>

      <Box p={4} borderTop="1px" borderColor="gray.200">
        <Flex>
          <Input
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder="Type a message..."
            mr={2}
            onKeyPress={handleKeyPress}
          />
          <IconButton
            aria-label="Send message"
            icon={<Send size={20} />}
            onClick={handleSendMessage}
            colorScheme={team === 'red' ? 'red' : team === 'blue' ? 'blue' : 'gray'}
          />
        </Flex>
      </Box>
    </Box>
  );
};

export default ChatWindow;
