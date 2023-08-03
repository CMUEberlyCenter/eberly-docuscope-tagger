<script lang="ts">
  import { AppBar } from "@skeletonlabs/skeleton";
  //import Statistics from './lib/Statistics.svelte';
  import Tagger from "./lib/Tagger.svelte";
</script>

<AppBar background="bg-primary-500">
  <a
    href="https://www.cmu.edu/dietrich/english/research/docuscope.html"
    class="text-white font-bold text-lg"
  >
    DocuScope
  </a>
</AppBar>
<Tagger />
