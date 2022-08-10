<script lang="ts">
  import { Navbar,NavbarBrand } from 'sveltestrap';
  //import Statistics from './lib/Statistics.svelte';
  import Tagger from './lib/Tagger.svelte';

</script>

<Navbar class="bg-primary">
  <NavbarBrand href="https://www.cmu.edu/dietrich/english/research/docuscope.html">DocuScope</NavbarBrand>
</Navbar>
<!--<TabContent class="my-2">
  <TabPane tabId="tag" tab="Tag Text" active>-->
    <Tagger/>
  <!--</TabPane>
  <TabPane tabId="stats" tab="Statistics">
    <Statistics/>
  </TabPane>
</TabContent>-->
