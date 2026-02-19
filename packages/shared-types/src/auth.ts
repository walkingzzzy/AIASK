export type AppRole = 'admin' | 'user';

export type User = {
  id: string;
  username: string;
  role: AppRole;
};

export type LoginResponse = {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: User;
};
