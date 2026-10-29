'use strict';
// Rewriting is explicit and CPU-only. Applying a draft never queues media generation.
help.promptAI=['AI prompt enhancer','Rewrite the current prompt locally using the optional Qwen2.5 1.5B Q4 model. Refine wording preserves the length; Add visual detail expands compatible visual detail. The model runs on CPU in a short-lived private process and uses no dedicated VRAM. Review and edit the draft before applying it. The AI may change details, so compare it with your original. Installing the pack downloads about 1.1 GB; generation quality and speed depend on the prompt and CPU.'];
const promptAITargets={iprompt:['image','Images'],eprompt:['edit','Image Editor'],vprompt:['video','Video'],fprompt:['faceswap','Faceswap'],aprompt:['avatar','Talking Avatar']};
let promptAIActive=null,promptAIRequest=false,promptAIInstall=false,promptAILastResult='',promptAIDraft=null,promptAIError='';
document.body.insertAdjacentHTML('beforeend',`<dialog id="prompt-ai-dialog" class="wide"><div class="dialog-heading"><h2>AI prompt enhancer</h2><button data-close aria-label="Close AI prompt enhancer">×</button></div><p id="prompt-ai-context" class="notice"></p><p>Local CPU model · compare the draft with your original before applying it.</p><div class="field"><label for="prompt-ai-mode">Refinement</label><select id="prompt-ai-mode"><option value="refine">Refine wording · preserve style and length</option><option value="expand">Add visual detail · preserve the subject and intent</option></select></div><div class="prompt-ai-comparison"><div class="field"><label for="prompt-ai-original">Original prompt</label><textarea id="prompt-ai-original" readonly></textarea></div><div class="field"><label for="prompt-ai-result">AI draft · editable</label><textarea id="prompt-ai-result" maxlength="12000" placeholder="The rewritten prompt will appear here…"></textarea></div></div><p id="prompt-ai-stage" class="notice" role="status"></p><div class="row"><button type="button" id="prompt-ai-install">Install &amp; enhance</button><button type="button" id="prompt-ai-run">Enhance again</button><button type="button" id="prompt-ai-cancel" hidden>Cancel prompt AI</button><button type="button" id="prompt-ai-apply" class="primary" disabled>Apply prompt</button><button data-close>Close</button></div></dialog>`);
for(const [id,[context,label]] of Object.entries(promptAITargets)){
 const field=$(id);if(!field)continue;
 const row=document.createElement('div');row.className='prompt-enhancer-action';row.innerHTML='<button type="button" data-prompt-ai="'+id+'">Enhance prompt with AI</button>'+q('promptAI');field.after(row);
 row.querySelector('button').onclick=()=>openPromptAI(id,context,label);
}
function acceptPromptAIDraft(result){
 if(!result||!promptAIActive||result.context!==promptAIActive.context||result.original!==promptAIActive.original)return;
 if(result.id!==promptAILastResult){promptAILastResult=result.id;promptAIDraft=result;$('prompt-ai-result').value=result.prompt;}
 $('prompt-ai-apply').disabled=!$('prompt-ai-result').value.trim()||$(promptAIActive.id).value.trim()!==promptAIActive.original;
}
function openPromptAI(id,context,label){
 const original=$(id).value.trim();if(!original){notify('Enter a prompt before enhancing it.');return;}if(original.length>4000){notify('Use up to 4000 characters for local prompt enhancement.');return;}
 promptAIActive={id,context,label,original};promptAIError='';$('prompt-ai-context').textContent=label+' · '+(state?.prompt_enhancer?.model||'Local prompt AI');$('prompt-ai-original').value=original;$('prompt-ai-result').value='';$('prompt-ai-apply').disabled=true;
 const cached=promptAIDraft?.original===original&&promptAIDraft.context===context?promptAIDraft:state?.prompt_enhancer?.result;
 promptAILastResult='';acceptPromptAIDraft(cached);$('prompt-ai-dialog').showModal();renderPromptAI();
 if(state?.prompt_enhancer?.ready&&!state.prompt_enhancer.busy&&!$('prompt-ai-result').value)runPromptAI();
}
async function runPromptAI(){
 if(!promptAIActive||promptAIRequest||state?.prompt_enhancer?.busy)return;
 if($(promptAIActive.id).value.trim()!==promptAIActive.original){promptAIError='The original prompt changed. Close this panel and reopen it for the updated prompt.';renderPromptAI();return;}
 promptAIRequest=true;promptAIError='';$('prompt-ai-apply').disabled=true;renderPromptAI();
 try{const response=await action('/api/prompts/enhance',{prompt:promptAIActive.original,context:promptAIActive.context,mode:$('prompt-ai-mode').value});acceptPromptAIDraft(response.result);if(!$('prompt-ai-dialog').open)notify('The AI prompt draft is ready. Reopen the enhancer to review it.');}
 catch(error){promptAIError=error.message;}
 finally{promptAIRequest=false;try{state=await api('/api/state');}catch{}renderPromptAI();}
}
async function installPromptAI(andEnhance=false){
 if(promptAIInstall||state?.prompt_enhancer?.busy)return;promptAIInstall=true;promptAIError='';renderPromptAI();
 try{await action('/api/prompts/install');state=await api('/api/state');if(andEnhance&&$('prompt-ai-dialog').open)runPromptAI();else notify('Local prompt AI installed.');}
 catch(error){promptAIError=error.message;}
 finally{promptAIInstall=false;renderPromptAI();}
}
$('prompt-ai-install').onclick=()=>installPromptAI(true);$('prompt-ai-run').onclick=runPromptAI;
$('prompt-ai-cancel').onclick=async()=>{try{const latest=await api('/api/state');await action('/api/prompts/cancel',{id:latest.prompt_enhancer.id});}catch(error){promptAIError=error.message;renderPromptAI();}};
$('prompt-ai-result').addEventListener('input',()=>{$('prompt-ai-apply').disabled=!$('prompt-ai-result').value.trim()||promptAIRequest;});
$('prompt-ai-apply').onclick=()=>{
 if(!promptAIActive||promptAIRequest)return;const field=$(promptAIActive.id),draft=$('prompt-ai-result').value.trim();if(!draft)return;
 if(field.value.trim()!==promptAIActive.original){promptAIError='Your prompt changed while the draft was being created. Reopen the enhancer for the updated prompt, or copy this draft.';$('prompt-ai-apply').disabled=true;renderPromptAI();return;}
 field.value=draft;field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));$('prompt-ai-dialog').close();notify('AI prompt applied.');
};
function renderPromptAI(){
 const info=state?.prompt_enhancer;if(!info)return;const busy=info.busy||promptAIRequest||promptAIInstall;
 document.querySelectorAll('[data-prompt-ai]').forEach(b=>b.disabled=!!busy);
 $('prompt-ai-install').hidden=!!info.ready;$('prompt-ai-install').disabled=!!busy;$('prompt-ai-run').hidden=!info.ready;$('prompt-ai-run').disabled=!!busy;$('prompt-ai-mode').disabled=!!busy;$('prompt-ai-cancel').hidden=!info.busy;
 $('prompt-ai-stage').textContent=promptAIError||(busy?(info.stage||'Working on the local CPU…'):info.error||($('prompt-ai-result').value?'Review and edit the draft, then apply it.':info.ready?'Ready to enhance this prompt.':'Install the optional prompt AI pack ('+(info.size/1024**3).toFixed(2)+' GB download).'));
 if(busy)$('prompt-ai-apply').disabled=true;else acceptPromptAIDraft(info.result);
 let card=$('prompt-ai-model-card');if(!card){card=document.createElement('article');card.id='prompt-ai-model-card';card.className='pack';card.dataset.vramTier='8';$('pack-grid').append(card);}
 const signature=JSON.stringify([info.ready,busy]);if(card.dataset.signature!==signature){card.dataset.signature=signature;card.innerHTML='<h3>AI prompt enhancer <span class="badge">'+(info.ready?'Installed':'Optional download')+'</span></h3><p>'+esc(info.model)+'</p><p>'+esc(info.note)+'</p><small>'+esc((info.size/1024**3).toFixed(2))+' GB download · '+esc(info.license)+' · <a href="'+esc(info.source)+'" target="_blank" rel="noreferrer">Model page ↗</a></small><button type="button" '+(busy?'disabled':'')+'>'+(info.ready?'Repair prompt AI':'Install prompt AI')+'</button>';card.querySelector('button').onclick=()=>installPromptAI(false);}
 applyVramFilter();
}
const beforePromptAITools=renderTools;renderTools=function(){beforePromptAITools();renderPromptAI();};
