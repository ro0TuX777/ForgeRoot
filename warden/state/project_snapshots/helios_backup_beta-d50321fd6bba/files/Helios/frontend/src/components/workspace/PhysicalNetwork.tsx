import React from 'react';
import { Box, Text, useColorModeValue } from '@chakra-ui/react';

const PhysicalNetwork: React.FC = () => {
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
      <Text>Physical Network View</Text>
      <Text>Status: Connected</Text>
      <Text>Physical Hosts: 8</Text>
      <Text>Network Switches: 2</Text>
      <Text>Physical Links: 16</Text>
      <Text>Bandwidth: 10Gbps</Text>
      <Text color="gray.500">{'>'}</Text>
    </Box>
  );
};

export default PhysicalNetwork;
