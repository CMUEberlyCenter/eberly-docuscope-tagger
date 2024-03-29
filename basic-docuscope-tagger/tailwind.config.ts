import { join } from 'path';
import type { Config } from 'tailwindcss';
import {default as forms} from '@tailwindcss/forms';

// 1. Import the Skeleton plugin
import { skeleton } from '@skeletonlabs/tw-plugin';

const config = {
	// 2. Opt for dark mode to be handled via the class method
	darkMode: 'class',
	content: [
		'./index.html',
		'./src/**/*.{html,js,svelte,ts}',
		// 3. Append the path to the Skeleton package
		join(require.resolve(
			'@skeletonlabs/skeleton'),
			'../**/*.{html,js,svelte,ts}'
		)
	],
	theme: {
		extend: {},
	},
	plugins: [
		forms,
		// 4. Append the Skeleton plugin (after other plugins)
		skeleton({
			themes: {
				// Register each theme within this array:
				preset: ["skeleton", "modern", "crimson"]
			}
		})
	]
} satisfies Config;

export default config;