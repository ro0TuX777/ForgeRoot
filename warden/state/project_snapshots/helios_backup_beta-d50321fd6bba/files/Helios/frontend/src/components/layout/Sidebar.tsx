import React, { useEffect } from 'react';
import { Box, VStack, Text, Avatar, Badge, Divider, useColorModeValue } from '@chakra-ui/react';
import { useUser } from '../../context/UserContext';
import getSocket from '../../utils/socket';

interface Operator {
  id: string;
  username: string;
  status: string;
  role: string;
}

const Sidebar: React.FC = () => {
  const { username } = useUser();
  const [operators, setOperators] = React.useState<Operator[]>([]);
  const socket = getSocket();

  useEffect(() => {
    if (!socket || !username) return;

    // Listen for active users list
    socket.on('activeUsers', (users: Operator[]) => {
      // Filter out duplicate users and sort by username
      const uniqueUsers = users.reduce((acc: Operator[], user) => {
        if (!acc.find(u => u.id === user.id)) {
          acc.push(user);
        }
        return acc;
      }, []).sort((a, b) => a.username.localeCompare(b.username));
      
      setOperators(uniqueUsers);
    });

    // Listen for user status updates
    socket.on('userStatusUpdate', ({ userId, status }: { userId: string; status: string }) => {
      setOperators(prev => {
        const updated = prev.map(op => 
          op.id === userId ? { ...op, status } : op
        );
        return updated.sort((a, b) => a.username.localeCompare(b.username));
      });
    });

    // Listen for new user joined
    socket.on('userJoined', (user: Operator) => {
      setOperators(prev => {
        // Don't add if user already exists
        if (prev.find(op => op.id === user.id)) {
          return prev;
        }
        const updated = [...prev, user];
        return updated.sort((a, b) => a.username.localeCompare(b.username));
      });
    });

    // Listen for user left
    socket.on('userLeft', (userId: string) => {
      setOperators(prev => prev.filter(op => op.id !== userId));
    });

    // Request initial active users list
    socket.emit('getActiveUsers');

    return () => {
      socket.off('activeUsers');
      socket.off('userStatusUpdate');
      socket.off('userJoined');
      socket.off('userLeft');
    };
  }, [socket, username]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online':
        return 'green';
      case 'away':
        return 'yellow';
      case 'offline':
        return 'gray';
      case 'SIGNED OUT':
        return 'red';
      default:
        return 'gray';
    }
  };

  return (
    <Box bg={useColorModeValue('white', 'blue.800')} h="full" rounded="lg" shadow="md" p={4}>
      {/* Current Mission */}
      <Box mb={6}>
        <Text fontSize="lg" fontWeight="bold" mb={2} color={useColorModeValue('black', 'white')}>
          Current Mission
        </Text>
        <Text color={useColorModeValue('gray.600', 'gray.300')} fontSize="sm">
          Operation Helios
        </Text>
        <Badge colorScheme="green" mt={2}>
          Active
        </Badge>
      </Box>

      <Divider mb={6} />

      {/* Operators */}
      <Box>
        <Text fontSize="lg" fontWeight="bold" mb={4} color={useColorModeValue('black', 'white')}>
          Operators
        </Text>
        <VStack spacing={4} align="stretch">
          {operators.map(operator => (
            <Box
              key={operator.id}
              p={3}
              bg={useColorModeValue('gray.50', 'blue.700')}
              rounded="md"
              display="flex"
              alignItems="center"
            >
              <Avatar size="sm" name={operator.username} mr={3} />
              <Box flex="1">
                <Text fontWeight="medium" color={useColorModeValue('black', 'white')}>
                  {operator.username}
                </Text>
                <Text fontSize="sm" color={useColorModeValue('gray.600', 'gray.300')}>
                  {operator.role}
                </Text>
              </Box>
              <Badge colorScheme={getStatusColor(operator.status)}>
                {operator.status}
              </Badge>
            </Box>
          ))}
        </VStack>
      </Box>

      <Divider my={6} />

      {/* Mission Stats */}
      <Box>
        <Text fontSize="lg" fontWeight="bold" mb={4} color={useColorModeValue('black', 'white')}>
          Mission Stats
        </Text>
        <VStack spacing={2} align="stretch">
          <Box>
            <Text fontSize="sm" color={useColorModeValue('gray.600', 'gray.300')}>
              Duration
            </Text>
            <Text fontWeight="medium" color={useColorModeValue('black', 'white')}>
              2h 45m
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" color={useColorModeValue('gray.600', 'gray.300')}>
              Active VMs
            </Text>
            <Text fontWeight="medium" color={useColorModeValue('black', 'white')}>
              3
            </Text>
          </Box>
          <Box>
            <Text fontSize="sm" color={useColorModeValue('gray.600', 'gray.300')}>
              Network Status
            </Text>
            <Badge colorScheme="green">Stable</Badge>
          </Box>
        </VStack>
      </Box>
    </Box>
  );
};

export default Sidebar;
