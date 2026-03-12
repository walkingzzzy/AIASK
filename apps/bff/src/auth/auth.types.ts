export type Role = 'admin' | 'user';

export type AppUser = {
  id: string;
  username: string;
  passwordHash: string;
  role: Role;
};

export type Session = {
  id: string;
  user: Omit<AppUser, 'passwordHash'>;
  accessJti: string;
  refreshToken: string;
  accessExpiresAt: number;
  refreshExpiresAt: number;
  revoked: boolean;
  createdAt: number;
  updatedAt: number;
};

export type AccessPayload = {
  sub: string;
  username: string;
  role: Role;
  jti: string;
  typ: 'access';
  exp: number;
  iat: number;
};
