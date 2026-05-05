import React from 'react';
import { Grid, GridItem, useColorModeValue } from '@chakra-ui/react';
import Header from './Header';
import Sidebar from './Sidebar';
import ChatWindow from '../shared/ChatWindow';
import WhiteCellChatWindow from '../shared/WhiteCellChatWindow';
import VMConsole from '../workspace/VMConsole';
import NotesPanel from '../workspace/NotesPanel';
import SharedDocuments from '../workspace/SharedDocuments';
import { useUser } from '../../context/UserContext';
import { Navigate } from 'react-router-dom';

const Workspace: React.FC = () => {
  const { isAuthenticated, team } = useUser();
  const bgColor = useColorModeValue('gray.50', 'gray.900');

  // Redirect to welcome page if not authenticated
  if (!isAuthenticated) {
    console.log('Not authenticated, redirecting to welcome page');
    return <Navigate to="/" replace />;
  }

  // Different layouts for White Cell vs other teams
  if (team === 'white') {
    return (
      <Grid
        h="100vh"
        templateRows="auto 1fr"
        templateColumns="250px 1fr 600px"
        templateAreas={{
          base: `
            "header header header"
            "sidebar main chat"
          `
        }}
        gap={4}
        p={4}
        bg={bgColor}
      >
        {/* Header */}
        <GridItem area="header" colSpan={3}>
          <Header />
        </GridItem>

        {/* Sidebar */}
        <GridItem area="sidebar">
          <Sidebar />
        </GridItem>

        {/* Main Content */}
        <GridItem area="main">
          <Grid
            h="full"
            templateRows="2fr 300px 300px"
            gap={4}
          >
            {/* VM Console */}
            <GridItem>
              <VMConsole />
            </GridItem>

            {/* Notes Panel */}
            <GridItem>
              <NotesPanel />
            </GridItem>

            {/* Shared Documents */}
            <GridItem>
              <SharedDocuments />
            </GridItem>
          </Grid>
        </GridItem>

        {/* White Cell Chat Windows */}
        <GridItem area="chat">
          <WhiteCellChatWindow />
        </GridItem>
      </Grid>
    );
  }

  // Regular team layout
  return (
    <Grid
      h="100vh"
      templateRows="auto 1fr"
      templateColumns="250px 1fr 300px"
      templateAreas={{
        base: `
          "header header header"
          "sidebar main chat"
        `
      }}
      gap={4}
      p={4}
      bg={bgColor}
    >
      {/* Header */}
      <GridItem area="header" colSpan={3}>
        <Header />
      </GridItem>

      {/* Sidebar */}
      <GridItem area="sidebar">
        <Sidebar />
      </GridItem>

      {/* Main Content */}
      <GridItem area="main">
        <Grid
          h="full"
          templateRows="2fr 300px 300px"
          gap={4}
        >
          {/* VM Console */}
          <GridItem>
            <VMConsole />
          </GridItem>

          {/* Notes Panel */}
          <GridItem>
            <NotesPanel />
          </GridItem>

          {/* Shared Documents */}
          <GridItem>
            <SharedDocuments />
          </GridItem>
        </Grid>
      </GridItem>

      {/* Team Chat Window */}
      <GridItem area="chat">
        <ChatWindow />
      </GridItem>
    </Grid>
  );
};

export default Workspace;
