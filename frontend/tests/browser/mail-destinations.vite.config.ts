import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';
export default defineConfig({root:path.resolve(__dirname,'../..'),envDir:false,plugins:[react(),tailwindcss()],resolve:{alias:{'@/lib/api':path.resolve(__dirname,'mail-destinations-api.ts'),'@':path.resolve(__dirname,'../../src')}},server:{host:'127.0.0.1',port:5182,strictPort:true}});
