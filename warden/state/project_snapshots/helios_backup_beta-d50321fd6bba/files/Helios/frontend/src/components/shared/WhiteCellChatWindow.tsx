import React, { useState, useEffect, useRef } from 'react';
import { Box, Flex, Text, Input, IconButton, VStack, Avatar, useColorModeValue, Grid, Button } from '@chakra-ui/react';
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
  timestamp: Date;
  team: string;
  sent_at?: string;
  delivered_at?: string;
}

const CHAT_HISTORY_LIMIT = 50;

const TeamChatPanel: React.FC<{
  title: string;
  messages: ChatMessage[];
  onSendMessage: (content: string, team: string) => void;
  team: string;
  borderColor: string;
  placeholder?: string;
  username: string;
}> = ({ title, messages, onSendMessage, team, borderColor, placeholder, username }) => {
  const [newMessage, setNewMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const bgColor = useColorModeValue('white', 'gray.800');

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const formatTime = (date: Date) => {
    const now = new Date();
    const diffInHours = (now.getTime() - new Date(date).getTime()) / (1000 * 60 * 60);

    // If message is from today, show time only
    if (diffInHours < 24 && new Date(date).getDate() === now.getDate()) {
      return new Intl.DateTimeFormat('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      }).format(new Date(date));
    }

    // If message is from this week, show day and time
    if (diffInHours < 168) { // 7 days
      return new Intl.DateTimeFormat('en-US', {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      }).format(new Date(date));
    }

    // Otherwise show full date and time
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }).format(new Date(date));
  };

  const handleSendMessage = () => {
    if (!newMessage.trim()) return;
    onSendMessage(newMessage.trim(), team);
    setNewMessage('');
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
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
      borderColor={borderColor}
    >
      <Flex p={4} borderBottom="1px" borderColor="gray.200" justify="space-between" align="center">
        <Text fontSize="lg" fontWeight="bold">
          {title}
        </Text>
        <Button
          leftIcon={<Download size={16} />}
          size="sm"
          colorScheme={team === 'red' ? 'red' : team === 'blue' ? 'blue' : 'purple'}
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
            const filename = `ChatLog_${username}_${team}_${fileTimestamp}.txt`;

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
            placeholder={placeholder || "Type a message..."}
            mr={2}
            onKeyPress={handleKeyPress}
          />
          <IconButton
            aria-label="Send message"
            icon={<Send size={20} />}
            onClick={handleSendMessage}
            colorScheme={team === 'red' ? 'red' : team === 'blue' ? 'blue' : 'purple'}
          />
        </Flex>
      </Box>
    </Box>
  );
};

const WhiteCellChatWindow: React.FC = () => {
  const [redTeamMessages, setRedTeamMessages] = useState<ChatMessage[]>([]);
  const [blueTeamMessages, setBlueTeamMessages] = useState<ChatMessage[]>([]);
  const [broadcastMessages, setBroadcastMessages] = useState<ChatMessage[]>([]);
  const { username, id: userId, team } = useUser();
  const socket = getSocket();

  useEffect(() => {
    if (!socket || !userId) return;

    // Join as White Cell
    socket.emit('joinTeam', { team: 'white', userId });
    console.log('White Cell joining teams');

    // Listen for team histories
    socket.on('redTeamHistory', (history: ChatMessage[]) => {
      console.log('Received Red Team history:', history);
      setRedTeamMessages(history.sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      ));
    });

    socket.on('blueTeamHistory', (history: ChatMessage[]) => {
      console.log('Received Blue Team history:', history);
      setBlueTeamMessages(history.sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      ));
    });

    // Listen for new messages
    socket.on('redTeamMessage', (message: ChatMessage) => {
      console.log('Received new Red Team message:', message);
      setRedTeamMessages(prev => [...prev, message].slice(-CHAT_HISTORY_LIMIT));
      // Send delivery confirmation
      socket.emit('messageDelivered', message.id);
    });

    socket.on('blueTeamMessage', (message: ChatMessage) => {
      console.log('Received new Blue Team message:', message);
      setBlueTeamMessages(prev => [...prev, message].slice(-CHAT_HISTORY_LIMIT));
      // Send delivery confirmation
      socket.emit('messageDelivered', message.id);
    });


    return () => {
      socket.off('redTeamHistory');
      socket.off('blueTeamHistory');
      socket.off('redTeamMessage');
      socket.off('blueTeamMessage');
    };
  }, [socket, userId]);

  const handleSendMessage = (content: string, targetTeam: string) => {
    if (!username || !userId) return;

    const message = {
      id: Date.now().toString(),
      sender: {
        id: userId,
        username: username
      },
      content,
      timestamp: new Date(),
      team: 'white',
      targetTeam
    };

    console.log(`Sending message to ${targetTeam}:`, message);
    socket.emit('sendMessage', message);
  };

  const handleBroadcastMessage = (content: string) => {
    if (!username || !userId) return;

    const message = {
      id: Date.now().toString(),
      sender: {
        id: userId,
        username: username
      },
      content,
      timestamp: new Date(),
      team: 'white',
      broadcast: true
    };

    console.log('Sending broadcast message:', message);
    socket.emit('sendMessage', message);
  };

  return (
    <Grid templateRows="auto 1fr" gap={4} h="full">
      {/* Broadcast Frame - Only show for White Cell */}
      {team === 'white' && (
        <Box>
          <TeamChatPanel
            title="Broadcast"
            messages={broadcastMessages}
            onSendMessage={handleBroadcastMessage}
            team="broadcast"
            borderColor="purple.500"
            placeholder="Enter broadcast message..."
            username={username || ''}
          />
        </Box>
      )}

      {/* Team Chats */}
      <Grid templateColumns="repeat(2, 1fr)" gap={4}>
        <TeamChatPanel
          title="Red Team Chat"
          messages={redTeamMessages}
          onSendMessage={handleSendMessage}
          team="red"
          borderColor="red.500"
          username={username || ''}
        />
        <TeamChatPanel
          title="Blue Team Chat"
          messages={blueTeamMessages}
          onSendMessage={handleSendMessage}
          team="blue"
          borderColor="blue.500"
          username={username || ''}
        />
      </Grid>
    </Grid>
  );
};

export default WhiteCellChatWindow;
