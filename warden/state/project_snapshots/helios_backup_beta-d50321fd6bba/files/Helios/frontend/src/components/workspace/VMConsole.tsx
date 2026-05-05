import React from 'react';
import { Box, Heading, Tabs, TabList, TabPanels, Tab, TabPanel, useColorModeValue, Text } from '@chakra-ui/react';
import LogicalNetwork from './LogicalNetwork';
import PhysicalNetwork from './PhysicalNetwork';
import SSHTerminal from '@/components/ssh/SSHTerminal';
import { useSSH } from '@/context/SSHContext';

const VMConsole: React.FC = () => {
  const { currentConnection } = useSSH();
  const bgColor = useColorModeValue('white', 'gray.800');
  const activeTabBg = useColorModeValue('black', 'gray.900');
  const activeTabColor = useColorModeValue('green.300', 'green.200');
  const consoleColor = useColorModeValue('green.300', 'green.200');

  return (
    <Box
      bg={bgColor}
      h="full"
      rounded="lg"
      shadow="md"
      p={4}
      display="flex"
      flexDirection="column"
    >
      <Heading size="md" mb={4}>
        Terminal
      </Heading>

      <Tabs variant="enclosed" flex="1" display="flex" flexDirection="column">
        <TabList>
          <Tab _selected={{ bg: activeTabBg, color: activeTabColor }}>
            {currentConnection ? `SSH: ${currentConnection.credentials.host}` : 'Console'}
          </Tab>
          <Tab _selected={{ bg: activeTabBg, color: activeTabColor }}>Logical Network</Tab>
          <Tab _selected={{ bg: activeTabBg, color: activeTabColor }}>Physical Network</Tab>
        </TabList>

        <TabPanels flex="1" display="flex" flexDirection="column">
          {/* Console Panel */}
          <TabPanel flex="1" p={0} mt={4}>
            {currentConnection ? (
              <SSHTerminal
                connectionId={currentConnection.id}
              />
            ) : (
              <Box
                bg="black"
                color={consoleColor}
                p={4}
                rounded="md"
                fontFamily="mono"
                flex="1"
                overflowY="auto"
                fontSize="sm"
              >
                <Text>Welcome to Helios VM Console</Text>
                <Text>Status: Connected</Text>
                <Text>Type 'help' for available commands</Text>
                <Text color="gray.500">{'>'}</Text>
              </Box>
            )}
          </TabPanel>

          {/* Logical Network Panel */}
          <TabPanel flex="1" p={0} mt={4}>
            <LogicalNetwork />
          </TabPanel>

          {/* Physical Network Panel */}
          <TabPanel flex="1" p={0} mt={4}>
            <PhysicalNetwork />
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
};

export default VMConsole;
