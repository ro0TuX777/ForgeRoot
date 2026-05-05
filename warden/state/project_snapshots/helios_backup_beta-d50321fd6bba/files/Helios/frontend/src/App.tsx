import React from 'react';
import { ChakraProvider, CSSReset } from '@chakra-ui/react';
import { 
  createBrowserRouter, 
  RouterProvider,
  Navigate
} from 'react-router-dom';
import { UserProvider } from '@/context/UserContext';
import { SSHProvider } from '@/context/SSHContext';
import Welcome from '@/components/Welcome';
import Workspace from '@/components/layout/Workspace';

const App: React.FC = () => {
  const router = createBrowserRouter([
    {
      path: "/",
      element: (
        <UserProvider>
          <SSHProvider>
            <Welcome />
          </SSHProvider>
        </UserProvider>
      )
    },
    {
      path: "/workspace",
      element: (
        <UserProvider>
          <SSHProvider>
            <Workspace />
          </SSHProvider>
        </UserProvider>
      )
    },
    {
      path: "*",
      element: <Navigate to="/" replace />
    }
  ]);

  return (
    <ChakraProvider>
      <CSSReset />
      <RouterProvider router={router} />
    </ChakraProvider>
  );
};

export default App;
