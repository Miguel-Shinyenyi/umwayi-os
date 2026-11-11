import '../../ui/src/style.css';
import { Document } from './document.js';

export const metadata = {
  title: 'umwayi-os',
  description: 'An AI operating system for one person. Your rules come before every AI helper acts, and every change is written down.',
};
export const viewport = { width: 'device-width', initialScale: 1, colorScheme: 'dark' };

export default function RootLayout({ children }) {
  return <Document>{children}</Document>;
}
