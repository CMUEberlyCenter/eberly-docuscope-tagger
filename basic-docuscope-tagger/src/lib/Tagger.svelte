<script lang="ts">
  import { fetchEventSource } from "@microsoft/fetch-event-source";
  import { ProgressBar } from "@skeletonlabs/skeleton";
  import { Temporal } from '@js-temporal/polyfill';

  const tagger_url = window.location.pathname.replace(/static.*$/, "tag");
  //const tagger_url = "https://docuscope.eberly.cmu.edu/tagger/tag";

  let resultColor:
    | "primary"
    | "secondary"
    | "tertiary"
    | "success"
    | "warning"
    | "error"
    | "surface" = "surface";
  let value = sessionStorage.getItem("text") ?? "";
  let tagged = "";
  let progress = 0;
  let tagging_time = 0;
  let word_count = 0;
  $: speed = word_count / (tagging_time > 0 ? tagging_time : 1);

  function tag(url: string, text: string) {
    const ctrl = new AbortController();
    resultColor = "warning";
    tagged = "Tagging...";
    sessionStorage.setItem("text", text);
    fetchEventSource(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ text }),
      signal: ctrl.signal,
      onerror(err) {
        console.error(err);
        tagged = err;
      },
      onmessage(msg) {
        switch (msg.event) {
          case "error":
            tagged = msg.data;
            resultColor = "error";
            console.error(msg.data);
            break;
          case "processing": {
            const processing = JSON.parse(msg.data);
            progress = processing.status;
            tagged += `${processing.status}...`;
            resultColor = "secondary";
            console.log(msg.data);
            break;
          }
          case "done": {
            const payload = JSON.parse(msg.data);
            tagged = payload.html_content;
            resultColor = "surface";
            tagging_time = Temporal.Duration.from(payload.tagging_time).total('second'); //payload.tagging_time;
            word_count = payload.word_count;
            console.log(msg.data);
            break;
          }
          case "": { // eat empty lines.
            // console.log('empty line');
            break;
          }
          default:
            console.warn(`Unhandled message ${msg}`);
        }
      },
    });
  }
  function submit() {
    const text = value.trim();
    tagging_time = 0;
    if (text !== "") {
      tag(tagger_url, text);
    } else {
      tagged = "Warning: no text to tag.";
      resultColor = "warning";
    }
  }
</script>

<div class="card p-2 m-2 border-2 border-primary-500">
  <header class="card-header">Enter Text:</header>
  <section>
    <textarea class="textarea" bind:value rows="20" cols="60" />
    <button type="button" class="btn variant-filled-secondary shadow shadow-blue-500/50" on:click={submit}>Submit</button>
  </section>
</div>
<div class="card p-2 m-2 border-2 border-secondary-500">
  <header class="card-header">
    Tagging Results: {word_count} words in {tagging_time}s ({speed} words/second)
  </header>
  <section>
    {#if progress > 0 && progress < 100}
      <ProgressBar label="Tagging progress." value={progress} max={100} />
    {/if}
    <aside class="alert {`variant-filled-${resultColor}`} tagging-results">
      <!-- eslint-disable-next-line svelte/no-at-html-tags -->
      {@html tagged}
    </aside>
  </section>
</div>
