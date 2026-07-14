const fs = require('fs');
const p = 'c:\\Users\\Administrator\\Desktop\\veimia-ugc-hub\\public\\js\\campaign.js';
let c = fs.readFileSync(p, 'utf8');

// Find the consent checkbox section and insert user_type radio before it
const marker = "data-field=\"consent\"";
const idx = c.indexOf(marker);
if (idx === -1) {
  console.log('ERROR: consent field not found');
  process.exit(1);
}

// Find the start of the consent div line (go back to find "html +=")
const beforeConsent = c.lastIndexOf("html += '", idx);

// New user type field HTML to insert
const userTypeField = `
    // User type (new/returning) radio buttons
    html += '<div class="form-field" data-field="user_type">';
    html += '<label>' + t('user_type_label') + '</label>';
    html += '<div style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap">';
    html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:400"><input type="radio" name="user_type" value="new" style="width:20px;height:20px;min-width:20px;min-height:20px"> ' + t('user_type_new') + '</label>';
    html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:400"><input type="radio" name="user_type" value="returning" style="width:20px;height:20px;min-width:20px;min-height:20px"> ' + t('user_type_returning') + '</label>';
    html += '</div>';
    html += '<span class="form-field__error"></span>';
    html += '</div>';

`;

// Insert before consent
c = c.slice(0, beforeConsent) + userTypeField + c.slice(beforeConsent);

// Also add consent detail text after the checkbox label
const consentAfter = "t('consent_label')";
const consentIdx = c.indexOf(consentAfter);
if (consentIdx > -1) {
  const afterConsentLabel = c.indexOf("</label>'", consentIdx);
  if (afterConsentLabel > -1) {
    const insertPoint = afterConsentLabel + "</label>'".length;
    const detailHtml = `
    html += '<p style="font-size:0.8rem;color:#888;margin-top:4px;line-height:1.5">' + t('consent_detail') + '</p>';`;
    // Find the next line after the label close
    const nextNewline = c.indexOf('\n', insertPoint);
    c = c.slice(0, nextNewline) + detailHtml + c.slice(nextNewline);
  }
}

fs.writeFileSync(p, c);
console.log('SUCCESS: Added user_type radio and consent detail');
