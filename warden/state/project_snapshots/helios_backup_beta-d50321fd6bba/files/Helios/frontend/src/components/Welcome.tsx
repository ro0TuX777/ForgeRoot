import React, { useState } from 'react';
import heliosLogo from '/blue-cloak-medium.png';
import { useNavigate } from 'react-router-dom';
import { setUsername } from '../utils/api';
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Input,
  VStack,
  Heading,
  Container,
  Image,
  Text,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  IconButton,
  useToast,
  Flex,
  Select
} from '@chakra-ui/react';
import { FaUser, FaUserAstronaut, FaUserNinja, FaUserSecret, FaUserTie } from 'react-icons/fa';
import { useUser } from '../context/UserContext';

const Welcome: React.FC = () => {
  const [username, setUsernameInput] = useState('');
  const [selectedIcon, setSelectedIcon] = useState('default');
  const [selectedTeam, setSelectedTeam] = useState('');
  const [selectedRole, setSelectedRole] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const icons = {
    default: FaUser,
    astronaut: FaUserAstronaut,
    ninja: FaUserNinja,
    secret: FaUserSecret,
    tie: FaUserTie
  };
  const navigate = useNavigate();
  const { setUser, clearUser } = useUser();
  const toast = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!username.trim()) {
      setError('Please enter a username');
      toast({
        title: 'Error',
        description: 'Please enter a username',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!selectedTeam) {
      setError('Please select a team');
      toast({
        title: 'Error',
        description: 'Please select a team',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (selectedTeam !== 'observer' && !selectedRole) {
      setError('Please select a role');
      toast({
        title: 'Error',
        description: 'Please select a role',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Clear any existing user data
      clearUser();

      const usernameTrimmed = username.trim();
      console.log('Setting username:', usernameTrimmed);

      const role = selectedTeam === 'observer' ? 'Observer' : selectedRole;
      const result = await setUsername(usernameTrimmed, selectedTeam, role);
      console.log('Server response:', result);

      if (!result.success || !result.data) {
        console.error('Error setting username:', result.error);
        setError(result.error || 'Failed to set username');
        toast({
          title: 'Error',
          description: result.error || 'Failed to set username',
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
        return;
      }

      const { id, username: serverUsername, status } = result.data;
      console.log('Setting user data:', { id, username: serverUsername, role, status, team: selectedTeam });
      
      // Store user data
      setUser(serverUsername, id, role, status, selectedTeam);
      
      // Store icon selection
      localStorage.setItem('helios_user_icon', selectedIcon);
      
      toast({
        title: 'Success',
        description: 'Workstation started successfully',
        status: 'success',
        duration: 3000,
        isClosable: true,
      });

      // Navigate to workspace
      navigate('/workspace');
    } catch (error) {
      console.error('Error during login:', error);
      setError('Failed to connect to server. Please try again.');
      toast({
        title: 'Error',
        description: 'Failed to connect to server',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Container maxW="container.sm" centerContent>
      <Box p={8} maxWidth="500px" borderWidth={1} borderRadius={8} boxShadow="lg" mt={20} bg="white">
        <VStack spacing={6} as="form" onSubmit={handleSubmit}>
          <Image src={heliosLogo} alt="Helios Logo" boxSize="150px" mb={4} style={{objectFit: 'contain'}} />
          <Heading color="black">Welcome to Helios</Heading>
          
          <FormControl isRequired>
            <FormLabel color="black">Choose your username</FormLabel>
            <Flex gap={4} mb={4}>
              <Input
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsernameInput(e.target.value)}
                autoComplete="off"
                flex="1"
                isDisabled={isLoading}
                bg="white"
                color="black"
                borderColor="black"
                borderWidth="1px"
              />
              <Menu>
                <MenuButton
                  as={IconButton}
                  aria-label="Select user icon"
                  icon={React.createElement(icons[selectedIcon as keyof typeof icons])}
                  variant="outline"
                  isDisabled={isLoading}
                  borderColor="black"
                  borderWidth="1px"
                  color="black"
                />
                <MenuList borderColor="black" borderWidth="1px">
                  {Object.entries(icons).map(([key, Icon]) => (
                    <MenuItem
                      key={key}
                      onClick={() => setSelectedIcon(key)}
                      icon={<Icon color="black" />}
                      _hover={{ bg: 'gray.100' }}
                    >
                      <Text color="black">{key.charAt(0).toUpperCase() + key.slice(1)} Icon</Text>
                    </MenuItem>
                  ))}
                </MenuList>
              </Menu>
            </Flex>

            <FormLabel color="black" mt={2}>Select your team</FormLabel>
            <Box position="relative" mb={4}>
              <Select
                value={selectedTeam}
                onChange={(e) => {
                  setSelectedTeam(e.target.value);
                  setSelectedRole(''); // Reset role when team changes
                }}
                placeholder="Choose a team"
                isRequired
                borderColor="black"
                borderWidth="1px"
                color="black"
                bg="white"
                sx={{
                  '& option': {
                    color: 'black',
                    background: 'white',
                    padding: '8px',
                  },
                  '&:focus': {
                    borderColor: 'blue.500',
                  }
                }}
              >
                <option value="red" style={{ backgroundColor: 'white', color: 'black' }}>Red Team</option>
                <option value="blue" style={{ backgroundColor: 'white', color: 'black' }}>Blue Team</option>
                <option value="white" style={{ backgroundColor: 'white', color: 'black' }}>White Cell</option>
                <option value="observer" style={{ backgroundColor: 'white', color: 'black' }}>Observer</option>
              </Select>
            </Box>

            {selectedTeam && selectedTeam !== 'observer' && (
              <>
                <FormLabel color="black">Select your role</FormLabel>
                <Box position="relative">
                  <Select
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value)}
                    placeholder="Choose a role"
                    isRequired
                    borderColor="black"
                    borderWidth="1px"
                    color="black"
                    bg="white"
                    sx={{
                      '& option': {
                        color: 'black',
                        background: 'white',
                        padding: '8px',
                      },
                      '&:focus': {
                        borderColor: 'blue.500',
                      }
                    }}
                  >
                    {selectedTeam === 'white' ? (
                      <>
                        <option value="Operational Test Director">Operational Test Director</option>
                        <option value="Network Support">Network Support</option>
                        <option value="User Support">User Support</option>
                        <option value="Test Support">Test Support</option>
                      </>
                    ) : (
                      <>
                        <option value="Mission Lead">Mission Lead</option>
                        <option value="Analyst">Analyst</option>
                        <option value="Technical Lead">Technical Lead</option>
                      </>
                    )}
                  </Select>
                </Box>
              </>
            )}
          </FormControl>

          {error && (
            <Text color="red.500" fontSize="sm">
              {error}
            </Text>
          )}

          <Button
            colorScheme="blue"
            type="submit"
            width="full"
            size="lg"
            isLoading={isLoading}
            loadingText="Starting..."
          >
            Start Workstation
          </Button>
        </VStack>
      </Box>
    </Container>
  );
};

export default Welcome;
