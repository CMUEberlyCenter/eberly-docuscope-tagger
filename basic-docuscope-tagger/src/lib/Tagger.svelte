<script lang="ts">
  import {
    Alert,
    Button,
    Card,
    CardBody,
    CardSubtitle,
    CardText,
    Progress,
  } from "sveltestrap";
  import { fetchEventSource } from "@microsoft/fetch-event-source";
  import type { AlertProps } from "sveltestrap/src/Alert";

  const tagger_url = window.location.pathname.replace(/static.*$/, 'tag');
  //const tagger_url = "https://docuscope.eberly.cmu.edu/tagger/tag";
  let resultColor: AlertProps["color"] = "info";
  let value = sessionStorage.getItem("text") ?? "";
  let tagged = "";
  let progress = 0;
  let tagging_time = 0;
  let word_count = 0;
  $: speed = word_count / (tagging_time > 0 ? tagging_time : 1);

  function tag(url: string, text: string) {
    const ctrl = new AbortController();
    resultColor = "info";
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
            resultColor = "danger";
            console.error(msg.data);
            break;
          case "processing":
            const processing = JSON.parse(msg.data);
            progress = processing.status;
            tagged += `${processing.status}...`;
            resultColor = "info";
            console.log(msg.data);
            break;
          case "done":
            const payload = JSON.parse(msg.data);
            tagged = payload.html_content;
            resultColor = "secondary";
            tagging_time = payload.tagging_time;
            word_count = payload.word_count;
            console.log(msg.data);
            break;
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

<Card class="m-1">
  <CardBody>
    <CardSubtitle>Enter Text:</CardSubtitle>
    <CardText>
      <textarea bind:value rows="20" cols="60" />
    </CardText>
    <Button on:click={submit}>Submit</Button>
  </CardBody>
</Card>
<Card class="m-1">
  <CardBody>
    <CardSubtitle>
      Tagging Results: {word_count} words in {tagging_time}s ({speed} words/second)
    </CardSubtitle>
    {#if progress > 0 && progress < 100}
      <Progress value={progress} />
    {/if}
    <Alert color={resultColor}>
      {@html tagged}
    </Alert>
  </CardBody>
</Card>
