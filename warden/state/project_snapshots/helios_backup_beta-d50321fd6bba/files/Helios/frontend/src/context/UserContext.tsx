import React, { createContext, useContext, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

interface User {
  id: string;
  username: string;
  role: string;
  status: string;
  team: string;
  isAuthenticated: boolean;
}

interface UserContextType {
  id: string | null;
  username: string | null;
  role: string | null;
  status: string | null;
  team: string | null;
  setUser: (username: string, id: string, role: string, status: string, team: string, isAuthenticated?: boolean) => void;
  clearUser: () => void;
  isAuthenticated: boolean;
}

const UserContext = createContext<UserContextType>({
  id: null,
  username: null,
  role: null,
  status: null,
  team: null,
  setUser: () => {},
  clearUser: () => {},
  isAuthenticated: false,
});

export function useUser() {
  return useContext(UserContext);
}

interface UserProviderProps {
  children: React.ReactNode;
}

export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [user, setUserState] = useState<User | null>(() => {
    const savedUser = localStorage.getItem('helios_user');
    return savedUser ? JSON.parse(savedUser) : null;
  });
  const navigate = useNavigate();

  const setUser = useCallback((username: string, id: string, role: string, status: string, team: string, isAuthenticated: boolean = true) => {
    const userData = { username, id, role, status, team, isAuthenticated };
    setUserState(userData);
    localStorage.setItem('helios_user', JSON.stringify(userData));
    console.log('User data set:', userData);
  }, []);

  const clearUser = useCallback(() => {
    console.log('Clearing user data');
    setUserState(null);
    localStorage.removeItem('helios_user');
    localStorage.removeItem('helios_user_team');
    navigate('/');
  }, [navigate]);

  const value = {
    id: user?.id || null,
    username: user?.username || null,
    role: user?.role || null,
    status: user?.status || null,
    team: user?.team || null,
    setUser,
    clearUser,
    isAuthenticated: user?.isAuthenticated || false,
  };

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};
