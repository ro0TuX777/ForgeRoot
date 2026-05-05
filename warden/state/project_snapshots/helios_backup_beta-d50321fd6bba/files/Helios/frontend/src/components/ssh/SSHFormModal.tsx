import React, { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalFooter,
  ModalBody,
  ModalCloseButton,
  Button,
  FormControl,
  FormLabel,
  Input,
  NumberInput,
  NumberInputField,
  VStack,
  Alert,
  AlertIcon,
  Textarea,
} from '@chakra-ui/react';
import { useSSH } from '@/context/SSHContext';
import { SSHCredentials } from '@/types/ssh';

interface SSHFormModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SSHFormModal: React.FC<SSHFormModalProps> = ({ isOpen, onClose }) => {
  const { connect, isConnecting, error } = useSSH();
  const [credentials, setCredentials] = useState<SSHCredentials>({
    host: '',
    port: 22,
    username: '',
    password: '',
    privateKey: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await connect(credentials);
    if (!error) {
      onClose();
      setCredentials({
        host: '',
        port: 22,
        username: '',
        password: '',
        privateKey: '',
      });
    }
  };

  const handleChange = (
    field: keyof SSHCredentials,
    value: string | number
  ) => {
    setCredentials(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <ModalOverlay />
      <ModalContent>
        <form onSubmit={handleSubmit}>
          <ModalHeader>SSH Connection</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={4}>
              {error && (
                <Alert status="error">
                  <AlertIcon />
                  {error}
                </Alert>
              )}
              <FormControl isRequired>
                <FormLabel>Host</FormLabel>
                <Input
                  value={credentials.host}
                  onChange={e => handleChange('host', e.target.value)}
                  placeholder="hostname or IP address"
                />
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Port</FormLabel>
                <NumberInput
                  value={credentials.port}
                  onChange={(_, value) => handleChange('port', value)}
                  min={1}
                  max={65535}
                  defaultValue={22}
                >
                  <NumberInputField />
                </NumberInput>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Username</FormLabel>
                <Input
                  value={credentials.username}
                  onChange={e => handleChange('username', e.target.value)}
                  placeholder="username"
                />
              </FormControl>
              <FormControl>
                <FormLabel>Password</FormLabel>
                <Input
                  type="password"
                  value={credentials.password}
                  onChange={e => handleChange('password', e.target.value)}
                  placeholder="password (optional if using private key)"
                />
              </FormControl>
              <FormControl>
                <FormLabel>Private Key</FormLabel>
                <Textarea
                  value={credentials.privateKey}
                  onChange={e => handleChange('privateKey', e.target.value)}
                  placeholder="Private key (optional if using password)"
                  rows={4}
                />
              </FormControl>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              type="submit"
              isLoading={isConnecting}
            >
              Connect
            </Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
};

export default SSHFormModal;
