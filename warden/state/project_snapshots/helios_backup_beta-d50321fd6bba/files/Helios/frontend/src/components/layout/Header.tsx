import React from 'react';
import {
  Box,
  Flex,
  Heading,
  Text,
  IconButton,
  Button,
  useColorMode,
  useColorModeValue,
  Tooltip,
} from '@chakra-ui/react';
import { Sun, Moon, LogOut } from 'lucide-react';
import { useUser } from '@/context/UserContext';
import SSHButton from '@/components/ssh/SSHButton';

const TeamBadge: React.FC<{ team: string }> = ({ team }) => {
  const getTeamStyles = () => {
    switch (team) {
      case 'red':
        return {
          bg: "rgba(127, 29, 29, 0.4)",
          color: "rgb(254, 226, 226)",
          border: "rgba(127, 29, 29, 0.3)",
          text: "RED TEAM"
        };
      case 'blue':
        return {
          bg: "rgba(30, 64, 175, 0.4)",
          color: "rgb(219, 234, 254)",
          border: "rgba(30, 64, 175, 0.3)",
          text: "BLUE TEAM"
        };
      case 'white':
        return {
          bg: "rgba(255, 255, 255, 0.15)",
          color: "rgb(255, 255, 255)",
          border: "rgba(255, 255, 255, 0.3)",
          text: "WHITE CELL"
        };
      case 'observer':
        return {
          bg: "rgba(202, 138, 4, 0.4)",
          color: "rgb(254, 249, 195)",
          border: "rgba(202, 138, 4, 0.3)",
          text: "OBSERVER"
        };
      default:
        return null;
    }
  };

  const styles = getTeamStyles();
  if (!styles) return null;

  return (
    <Box
      as="span"
      px="3"
      py="1"
      mr={2}
      rounded="md"
      fontSize="sm"
      fontWeight="medium"
      bg={styles.bg}
      color={styles.color}
      border="1px"
      borderColor={styles.border}
    >
      {styles.text}
    </Box>
  );
};

const Header: React.FC = () => {
  const { colorMode, toggleColorMode } = useColorMode();
  const { username, team, clearUser } = useUser();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  return (
    <Box
      as="header"
      bg={bgColor}
      borderBottom="1px"
      borderColor={borderColor}
      py={4}
      px={6}
      rounded="lg"
      shadow="sm"
    >
      <Flex justify="space-between" align="center">
        <Flex align="center" gap={2}>
          <Heading size="md">HELIOS</Heading>
          <Text fontSize="sm" color="gray.500" fontStyle="italic">
            (Hybrid Environment for Linked Intelligence Operations System)
          </Text>
        </Flex>

        <Flex align="center" gap={4}>
          {username && (
            <Flex align="center">
              {team && <TeamBadge team={team} />}
              <Text fontSize="sm" color="gray.500">
                Operator: {username}
              </Text>
            </Flex>
          )}
          <Flex gap={2}>
            <SSHButton />
            <Tooltip label={`Switch to ${colorMode === 'light' ? 'dark' : 'light'} mode`}>
              <IconButton
                aria-label="Toggle color mode"
                icon={colorMode === 'light' ? <Moon size={20} /> : <Sun size={20} />}
                onClick={toggleColorMode}
                size="sm"
                variant="ghost"
              />
            </Tooltip>
            <Button
              leftIcon={<LogOut size={20} />}
              onClick={clearUser}
              size="sm"
              colorScheme="red"
              variant="ghost"
            >
              Log Out
            </Button>
          </Flex>
        </Flex>
      </Flex>
    </Box>
  );
};

export default Header;
