import React, { useState } from 'react';
import { Button, useDisclosure } from '@chakra-ui/react';
import { useSSH } from '@/context/SSHContext';
import SSHFormModal from './SSHFormModal';

const SSHButton: React.FC = () => {
  const { isOpen, onOpen, onClose } = useDisclosure();
  const { currentConnection, disconnect } = useSSH();
  const [isLoading, setIsLoading] = useState(false);

  const handleDisconnect = async () => {
    setIsLoading(true);
    await disconnect();
    setIsLoading(false);
  };

  return (
    <>
      {currentConnection ? (
        <Button
          colorScheme="green"
          isLoading={isLoading}
          onClick={handleDisconnect}
          size="sm"
        >
          Connected to {currentConnection.credentials.host}
        </Button>
      ) : (
        <Button
          colorScheme="blue"
          onClick={onOpen}
          size="sm"
        >
          Connect SSH
        </Button>
      )}

      <SSHFormModal isOpen={isOpen} onClose={onClose} />
    </>
  );
};

export default SSHButton;
