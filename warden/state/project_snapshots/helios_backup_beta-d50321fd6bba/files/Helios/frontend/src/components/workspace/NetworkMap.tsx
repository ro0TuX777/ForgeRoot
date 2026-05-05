import React from 'react';
import {
  Box,
  Text,
  HStack,
  VStack,
  Button,
  Badge,
  useColorModeValue,
} from '@chakra-ui/react';
import { Network, Shield, AlertTriangle } from 'lucide-react';

interface NetworkNode {
  id: string;
  name: string;
  type: 'vm' | 'router' | 'switch';
  status: 'active' | 'warning' | 'error';
  connections: string[];
}

// Mock data - replace with actual network data
const networkNodes: NetworkNode[] = [
  {
    id: '1',
    name: 'VM-Alpha-1',
    type: 'vm',
    status: 'active',
    connections: ['2'],
  },
  {
    id: '2',
    name: 'Router-1',
    type: 'router',
    status: 'active',
    connections: ['1', '3'],
  },
  {
    id: '3',
    name: 'Switch-1',
    type: 'switch',
    status: 'warning',
    connections: ['2'],
  },
];

const NetworkMap: React.FC = () => {
  const bgColor = useColorModeValue('white', 'gray.800');

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'green';
      case 'warning':
        return 'yellow';
      case 'error':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getNodeIcon = (type: string) => {
    switch (type) {
      case 'router':
        return <Network size={20} />;
      case 'switch':
        return <Shield size={20} />;
      default:
        return <Box w={5} h={5} rounded="full" bg="blue.500" />;
    }
  };

  return (
    <Box h="full" bg={bgColor} rounded="md" p={4}>
      {/* Network Controls */}
      <HStack spacing={4} mb={4}>
        <Button size="sm" leftIcon={<Network size={16} />}>
          Refresh
        </Button>
        <Button size="sm" leftIcon={<AlertTriangle size={16} />}>
          Run Scan
        </Button>
      </HStack>

      {/* Network Status */}
      <Box mb={6}>
        <Text fontSize="lg" fontWeight="bold" mb={2}>
          Network Status
        </Text>
        <HStack spacing={4}>
          <Badge colorScheme="green">3 Active Nodes</Badge>
          <Badge colorScheme="yellow">1 Warning</Badge>
          <Badge colorScheme="red">0 Errors</Badge>
        </HStack>
      </Box>

      {/* Network Nodes */}
      <VStack align="stretch" spacing={4}>
        {networkNodes.map((node) => (
          <Box
            key={node.id}
            p={4}
            bg="gray.50"
            rounded="md"
            borderLeft="4px"
            borderColor={`${getStatusColor(node.status)}.500`}
          >
            <HStack justify="space-between">
              <HStack>
                {getNodeIcon(node.type)}
                <VStack align="start" spacing={1}>
                  <Text fontWeight="medium">{node.name}</Text>
                  <Text fontSize="sm" color="gray.600">
                    {node.type.toUpperCase()} • {node.connections.length} connections
                  </Text>
                </VStack>
              </HStack>
              <Badge colorScheme={getStatusColor(node.status)}>
                {node.status}
              </Badge>
            </HStack>
          </Box>
        ))}
      </VStack>

      {/* Network Metrics */}
      <Box mt={6}>
        <Text fontSize="lg" fontWeight="bold" mb={2}>
          Network Metrics
        </Text>
        <VStack align="stretch" spacing={2}>
          <HStack justify="space-between">
            <Text color="gray.600">Bandwidth Usage</Text>
            <Text fontWeight="medium">45 Mbps</Text>
          </HStack>
          <HStack justify="space-between">
            <Text color="gray.600">Latency</Text>
            <Text fontWeight="medium">12 ms</Text>
          </HStack>
          <HStack justify="space-between">
            <Text color="gray.600">Packet Loss</Text>
            <Text fontWeight="medium">0.1%</Text>
          </HStack>
        </VStack>
      </Box>
    </Box>
  );
};

export default NetworkMap;
