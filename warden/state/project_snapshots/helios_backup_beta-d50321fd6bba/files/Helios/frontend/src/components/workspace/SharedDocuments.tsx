import React, { useState, useEffect, useRef } from 'react';
import { listDocuments, getDocument, uploadDocument, shareDocuments, deleteDocument } from '../../utils/api';
import { useUser } from '../../context/UserContext';
import { getSocket } from '../../utils/socket';
import {
  Box,
  Text,
  Select,
  Grid,
  Button,
  HStack,
  useColorModeValue,
  VStack,
  useToast,
  IconButton,
  Collapse,
} from '@chakra-ui/react';
import { FaUpload, FaPaperPlane, FaArrowLeft, FaTimes, FaChevronDown, FaChevronUp } from 'react-icons/fa';

interface Document {
  name: string;
  size: number;
  modified: Date;
  selected?: boolean;
}

interface UserData {
  team: string | null;
  role: string | null;
  username: string | null;
  id: string | null;
  status: string | null;
  isAuthenticated: boolean;
}

const SharedDocuments: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [whiteCellDocuments, setWhiteCellDocuments] = useState<Document[]>([]);
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [documentContent, setDocumentContent] = useState<string>('');
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [selectedDocumentTeam, setSelectedDocumentTeam] = useState<string | null>(null);
  const [selectedWhiteCellDocument, setSelectedWhiteCellDocument] = useState<string>('');
  const [selectedTargetTeam, setSelectedTargetTeam] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);
  
  const userData = useUser() as UserData;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');
  const previewBg = useColorModeValue('gray.50', 'gray.700');
  const toast = useToast();

  const isWhiteCell = userData?.team === 'white' && userData?.role === 'Operational Test Director' && userData?.isAuthenticated;

  useEffect(() => {
    if (userData?.team && userData?.isAuthenticated) {
      const socket = getSocket();
      
      if (userData.team && userData.username && userData.role) {
        socket.emit('updateUserInfo', {
          team: userData.team,
          username: userData.username,
          role: userData.role,
          isAuthenticated: userData.isAuthenticated
        });

        socket.on('userAuthenticated', ({ success, isAuthenticated }) => {
          if (success && isAuthenticated) {
            socket.emit('joinTeam', userData.team);
          }
        });
      }

      socket.on('documentsUpdated', ({ team }) => {
        if (team === userData.team) {
          loadDocuments();
        }
      });

      socket.on('userAuthenticated', ({ success, isAuthenticated }) => {
        if (success && isAuthenticated) {
          loadDocuments();
          if (isWhiteCell) {
            loadWhiteCellDocuments();
          }
        }
      });

      return () => {
        socket.off('documentsUpdated');
        socket.off('userAuthenticated');
      };
    }
  }, [userData.team, isWhiteCell]);

  useEffect(() => {
    const socket = getSocket();
    socket.on('connect', () => {
      if (userData.team && userData.username && userData.role) {
        socket.emit('updateUserInfo', {
          team: userData.team,
          username: userData.username,
          role: userData.role,
          isAuthenticated: userData.isAuthenticated
        });
      }
    });
    return () => {
      socket.off('connect');
    };
  }, [isWhiteCell, userData.team, userData.username, userData.role]);

  useEffect(() => {
    if (selectedDocument && selectedDocumentTeam) {
      loadDocumentContent(selectedDocument, selectedDocumentTeam);
    } else {
      setDocumentContent('');
    }
  }, [selectedDocument, selectedDocumentTeam]);

  const loadDocuments = async () => {
    try {
      setIsLoading(true);
      if (!userData.team) return;
      const result = await listDocuments(userData.team);
      if (result.success && result.data) {
        setDocuments(result.data.map(doc => ({ ...doc, selected: false })));
      } else {
        toast({
          title: 'Error',
          description: result.error || 'Failed to load documents',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load documents',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const loadWhiteCellDocuments = async () => {
    try {
      const result = await listDocuments('white');
      if (result.success && result.data) {
        setWhiteCellDocuments(result.data.map(doc => ({ ...doc, selected: false })));
      } else {
        toast({
          title: 'Error',
          description: result.error || 'Failed to load White Cell documents',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load White Cell documents',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  };

  const loadDocumentContent = async (filename: string, team: string) => {
    try {
      setIsLoading(true);
      const result = await getDocument(team, filename);
      if (result.success && result.data) {
        setDocumentContent(result.data);
      } else {
        toast({
          title: 'Error',
          description: result.error || 'Failed to load document content',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load document content',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    if (!file.name.match(/\.(txt|pdf)$/)) {
      toast({
        title: 'Error',
        description: 'Only .txt and .pdf files are allowed',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsLoading(true);
      const result = await uploadDocument('white', file);
      if (result.success) {
        toast({
          title: 'Success',
          description: 'File uploaded successfully',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        loadWhiteCellDocuments();
      } else {
        toast({
          title: 'Error',
          description: result.error || 'Failed to upload file',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to upload file',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleWhiteCellDocumentSelect = (docName: string) => {
    setSelectedWhiteCellDocument(docName);
    setSelectedDocument(docName);
    setSelectedDocumentTeam('white');
  };

  const handleTargetTeamSelect = (team: string) => {
    setSelectedTargetTeam(team);
    if (team === 'all') {
      setSelectedTeams(['red', 'blue']);
    } else {
      setSelectedTeams([team]);
    }
  };

  const handleSendDocuments = async () => {
    if (!selectedWhiteCellDocument || !selectedTargetTeam) {
      toast({
        title: 'Error',
        description: 'Please select both a document and target team',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsLoading(true);
      if (!userData.isAuthenticated || userData.team !== 'white' || userData.role !== 'Operational Test Director') {
        toast({
          title: 'Error',
          description: 'Only White Cell Operational Test Director can share documents',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        return;
      }

      const result = await shareDocuments([selectedWhiteCellDocument], selectedTeams);
      
      await loadWhiteCellDocuments();
      if (result.success) {
        toast({
          title: 'Success',
          description: 'Documents shared successfully',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
        setSelectedWhiteCellDocument('');
        setSelectedTargetTeam('');
        setSelectedTeams([]);
      } else {
        toast({
          title: 'Error',
          description: result.error || 'Failed to share documents',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to share documents',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Box
      bg={bgColor}
      h={isExpanded ? "full" : "auto"}
      rounded="lg"
      shadow="md"
      display="flex"
      flexDirection="column"
    >
      <Box 
        p={4} 
        borderBottom={isExpanded ? "1px" : "none"} 
        borderColor="gray.200"
        cursor="pointer"
        onClick={() => setIsExpanded(!isExpanded)}
        display="flex"
        alignItems="center"
        justifyContent="space-between"
      >
        <Text fontSize="lg" fontWeight="bold">
          Team Documents
        </Text>
        <IconButton
          aria-label={isExpanded ? "Collapse panel" : "Expand panel"}
          icon={isExpanded ? <FaChevronUp /> : <FaChevronDown />}
          size="sm"
          variant="ghost"
        />
      </Box>

      <Collapse in={isExpanded} animateOpacity>
        <Box p={4} flex="1">
          <Grid templateColumns="250px 1fr" gap={4} h="full">
            {/* Left Panel - Controls */}
            <VStack spacing={4} align="stretch" h="full" overflowY="auto">
              {isWhiteCell && (
                <>
                  {/* White Cell Documents */}
                  <Box>
                    <Text fontWeight="medium" mb={2}>White Cell Documents:</Text>
                    <Select
                      value={selectedWhiteCellDocument}
                      onChange={(e) => handleWhiteCellDocumentSelect(e.target.value)}
                      placeholder="Select a document"
                      mb={4}
                      isDisabled={isLoading}
                    >
                      {whiteCellDocuments.map(doc => (
                        <option key={doc.name} value={doc.name}>
                          {doc.name}
                        </option>
                      ))}
                    </Select>
                  </Box>

                  {/* Send to */}
                  <Box>
                    <Text fontWeight="medium" mb={2}>Send to:</Text>
                    <Select
                      value={selectedTargetTeam}
                      onChange={(e) => handleTargetTeamSelect(e.target.value)}
                      placeholder="Select target team"
                      mb={4}
                      isDisabled={isLoading}
                    >
                      <option value="red">Red Team</option>
                      <option value="blue">Blue Team</option>
                      <option value="all">All Teams</option>
                    </Select>

                    <Button
                      leftIcon={<FaPaperPlane />}
                      onClick={handleSendDocuments}
                      colorScheme="green"
                      isDisabled={isLoading || !selectedWhiteCellDocument || !selectedTargetTeam}
                      w="full"
                      mb={4}
                    >
                      Send Out
                    </Button>
                  </Box>
                </>
              )}

              {/* Team Documents */}
              <Box flex="1" overflowY="auto">
                <Text fontWeight="medium" mb={2}>Team Documents:</Text>
                <VStack align="stretch" spacing={2}>
                  {documents.map(doc => (
                    <HStack key={doc.name} spacing={0} align="center">
                      <Text
                        cursor="pointer"
                        onClick={() => {
                          setSelectedDocument(doc.name);
                          if (userData.team) {
                            setSelectedDocumentTeam(userData.team);
                          }
                        }}
                        color={selectedDocument === doc.name && selectedDocumentTeam === userData.team ? 'blue.500' : undefined}
                        _hover={{ textDecoration: 'underline' }}
                      >
                        {doc.name}
                      </Text>
                      {doc.name.endsWith('.txt') && (
                        <IconButton
                          aria-label="Delete document"
                          icon={<FaTimes />}
                          size="xs"
                          colorScheme="red"
                          variant="ghost"
                          p={0}
                          minW={0}
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (userData.team) {
                              const result = await deleteDocument(userData.team, doc.name);
                              if (result.success) {
                                loadDocuments();
                                if (selectedDocument === doc.name) {
                                  setSelectedDocument(null);
                                  setDocumentContent('');
                                }
                              } else {
                                toast({
                                  title: 'Error',
                                  description: result.error || 'Failed to delete document',
                                  status: 'error',
                                  duration: 3000,
                                  isClosable: true,
                                });
                              }
                            }
                          }}
                        />
                      )}
                    </HStack>
                  ))}
                </VStack>
              </Box>
            </VStack>

            {/* Right Panel - Document Preview */}
            <Box
              bg={previewBg}
              p={4}
              rounded="md"
              border="1px"
              borderColor={borderColor}
              overflowY="auto"
              h="full"
            >
              {isWhiteCell && (
                <HStack mb={4} spacing={2} justify="flex-start">
                  <Button
                    leftIcon={<FaUpload />}
                    onClick={handleFileSelect}
                    colorScheme="blue"
                    isDisabled={isLoading}
                    size="md"
                    variant="outline"
                    px={4}
                  >
                    Select Source File
                  </Button>
                  {documentContent && (
                    <IconButton
                      aria-label="Back to documents"
                      icon={<FaArrowLeft />}
                      size="md"
                      colorScheme="blue"
                      variant="outline"
                      onClick={() => {
                        setDocumentContent('');
                        setSelectedDocument(null);
                        setSelectedDocumentTeam(null);
                      }}
                    />
                  )}
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".txt,.pdf"
                    style={{ display: 'none' }}
                  />
                </HStack>
              )}
              <Box fontFamily="mono" fontSize="sm" h="full">
                {documentContent ? (
                  <Text whiteSpace="pre-wrap">{documentContent}</Text>
                ) : (
                  <Text color="gray.500">Select a document to view its content</Text>
                )}
              </Box>
            </Box>
          </Grid>
        </Box>
      </Collapse>
    </Box>
  );
};

export default SharedDocuments;
