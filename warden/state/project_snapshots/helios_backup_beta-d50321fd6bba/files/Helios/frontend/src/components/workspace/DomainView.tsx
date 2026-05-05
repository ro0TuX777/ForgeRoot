import React from 'react';
import {
  Box,
  Text,
  Grid,
  GridItem,
  VStack,
  HStack,
  Badge,
  Progress,
  useColorModeValue,
} from '@chakra-ui/react';
import { Globe, Server, Database, Shield } from 'lucide-react';

interface DomainResource {
  id: string;
  name: string;
  type: 'server' | 'database' | 'service';
  status: 'operational' | 'degraded' | 'critical';
  metrics: {
    cpu: number;
    memory: number;
    storage: number;
  };
}

// Mock data - replace with actual domain data
const domainResources: DomainResource[] = [
  {
    id: '1',
    name: 'Primary Web Server',
    type: 'server',
    status: 'operational',
    metrics: {
      cpu: 45,
      memory: 60,
      storage: 30,
    },
  },
  {
    id: '2',
    name: 'User Database',
    type: 'database',
    status: 'degraded',
    metrics: {
      cpu: 75,
      memory: 85,
      storage: 70,
    },
  },
  {
    id: '3',
    name: 'Auth Service',
    type: 'service',
    status: 'operational',
    metrics: {
      cpu: 25,
      memory: 40,
      storage: 20,
    },
  },
];

const DomainView: React.FC = () => {
  const bgColor = useColorModeValue('white', 'gray.800');

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'operational':
        return 'green';
      case 'degraded':
        return 'yellow';
      case 'critical':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getResourceIcon = (type: string) => {
    switch (type) {
      case 'server':
        return <Server size={20} />;
      case 'database':
        return <Database size={20} />;
      case 'service':
        return <Shield size={20} />;
      default:
        return <Globe size={20} />;
    }
  };

  const getMetricColor = (value: number) => {
    if (value >= 80) return 'red';
    if (value >= 60) return 'yellow';
    return 'green';
  };

  return (
    <Box h="full" bg={bgColor} rounded="md" p={4}>
      {/* Domain Overview */}
      <Box mb={6}>
        <Text fontSize="lg" fontWeight="bold" mb={2}>
          Domain Overview
        </Text>
        <HStack spacing={4}>
          <Badge colorScheme="green">2 Operational</Badge>
          <Badge colorScheme="yellow">1 Degraded</Badge>
          <Badge colorScheme="red">0 Critical</Badge>
        </HStack>
      </Box>

      {/* Resources Grid */}
      <Grid templateColumns="repeat(auto-fill, minmax(300px, 1fr))" gap={4}>
        {domainResources.map((resource) => (
          <GridItem key={resource.id}>
            <Box
              p={4}
              bg="gray.50"
              rounded="lg"
              borderTop="4px"
              borderColor={`${getStatusColor(resource.status)}.500`}
            >
              <HStack mb={4}>
                {getResourceIcon(resource.type)}
                <VStack align="start" spacing={0}>
                  <Text fontWeight="medium">{resource.name}</Text>
                  <Text fontSize="sm" color="gray.600">
                    {resource.type.charAt(0).toUpperCase() + resource.type.slice(1)}
                  </Text>
                </VStack>
                <Badge ml="auto" colorScheme={getStatusColor(resource.status)}>
                  {resource.status}
                </Badge>
              </HStack>

              {/* Resource Metrics */}
              <VStack align="stretch" spacing={3}>
                <Box>
                  <HStack justify="space-between" mb={1}>
                    <Text fontSize="sm">CPU Usage</Text>
                    <Text fontSize="sm" fontWeight="medium">
                      {resource.metrics.cpu}%
                    </Text>
                  </HStack>
                  <Progress
                    value={resource.metrics.cpu}
                    size="sm"
                    colorScheme={getMetricColor(resource.metrics.cpu)}
                  />
                </Box>
                <Box>
                  <HStack justify="space-between" mb={1}>
                    <Text fontSize="sm">Memory Usage</Text>
                    <Text fontSize="sm" fontWeight="medium">
                      {resource.metrics.memory}%
                    </Text>
                  </HStack>
                  <Progress
                    value={resource.metrics.memory}
                    size="sm"
                    colorScheme={getMetricColor(resource.metrics.memory)}
                  />
                </Box>
                <Box>
                  <HStack justify="space-between" mb={1}>
                    <Text fontSize="sm">Storage Usage</Text>
                    <Text fontSize="sm" fontWeight="medium">
                      {resource.metrics.storage}%
                    </Text>
                  </HStack>
                  <Progress
                    value={resource.metrics.storage}
                    size="sm"
                    colorScheme={getMetricColor(resource.metrics.storage)}
                  />
                </Box>
              </VStack>
            </Box>
          </GridItem>
        ))}
      </Grid>
    </Box>
  );
};

export default DomainView;
