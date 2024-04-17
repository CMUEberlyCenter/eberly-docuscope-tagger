import globals from "globals";
import pluginJs from "@eslint/js";
import tseslint from "typescript-eslint";
import eslintPluginSvelte from "eslint-plugin-svelte";
import tsparser from '@typescript-eslint/parser';
import svelteparser from 'svelte-eslint-parser';

export default [
    {
	languageOptions: {
	    globals: globals.browser,
	}
    },
    {
	files: ["**/*.svelte"],
	languageOptions: {
	    globals: globals.browser,
	    parser: svelteparser,
	    parserOptions: {
		parser: '@typescript-eslint/parser',
		project: './tsconfig.json',
		extraFileExtensions: ['.svelte'],
	    },
	}
    },
    pluginJs.configs.recommended,
    ...tseslint.configs.recommended,
    ...eslintPluginSvelte.configs['flat/prettier'],
];
