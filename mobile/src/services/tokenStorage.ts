import { deleteItemAsync, getItemAsync, setItemAsync } from './secureStore';

const ACCESS_TOKEN_KEY = 'tradamind_mobile_access_token';
const REFRESH_TOKEN_KEY = 'tradamind_mobile_refresh_token';

let accessTokenCache: string | null = null;
let refreshTokenCache: string | null = null;

export async function getAccessToken() {
  if (accessTokenCache !== null) return accessTokenCache;
  accessTokenCache = await getItemAsync(ACCESS_TOKEN_KEY);
  return accessTokenCache;
}

export async function getRefreshToken() {
  if (refreshTokenCache !== null) return refreshTokenCache;
  refreshTokenCache = await getItemAsync(REFRESH_TOKEN_KEY);
  return refreshTokenCache;
}

export async function saveTokens(accessToken: string, refreshToken: string) {
  accessTokenCache = accessToken;
  refreshTokenCache = refreshToken;
  await Promise.all([
    setItemAsync(ACCESS_TOKEN_KEY, accessToken),
    setItemAsync(REFRESH_TOKEN_KEY, refreshToken),
  ]);
}

export async function saveAccessToken(accessToken: string) {
  accessTokenCache = accessToken;
  await setItemAsync(ACCESS_TOKEN_KEY, accessToken);
}

export async function clearTokens() {
  accessTokenCache = null;
  refreshTokenCache = null;
  await Promise.all([
    deleteItemAsync(ACCESS_TOKEN_KEY),
    deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}
