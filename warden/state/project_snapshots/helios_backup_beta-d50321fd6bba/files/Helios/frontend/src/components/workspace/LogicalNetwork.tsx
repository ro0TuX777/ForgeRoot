import React from 'react';
import { Box, Text, useColorModeValue } from '@chakra-ui/react';

const LogicalNetwork: React.FC = () => {
  const bgColor = useColorModeValue('black', 'gray.900');
  const textColor = useColorModeValue('green.300', 'green.200');

  return (
    <Box
      bg={bgColor}
      color={textColor}
      p={4}
      rounded="md"
      fontFamily="mono"
      flex="1"
      overflowY="auto"
      fontSize="sm"
    >
      <Text>Logical Network View</Text>
      <Text>Status: Connected</Text>
      <Text>Network Topology: Mesh</Text>
      <Text>Virtual Interfaces: 4</Text>
      <Text>Active Routes: 12</Text>
      <Text>Security Groups: 3</Text>
      <Text color="gray.500">{'>'}</Text>
    </Box>
  );
};

export default LogicalNetwork;
