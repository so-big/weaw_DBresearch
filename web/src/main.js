import { mount } from 'svelte';
import '@fontsource/kanit/500.css';
import '@fontsource/kanit/600.css';
import '@fontsource/ibm-plex-sans-thai/400.css';
import '@fontsource/ibm-plex-sans-thai/500.css';
import '@fontsource/ibm-plex-sans-thai/600.css';
import './app.css';
import App from './App.svelte';
import { startRouter } from './lib/router.svelte.js';
import { initTheme } from './lib/state.svelte.js';

initTheme();
startRouter();
mount(App, { target: document.getElementById('app') });
