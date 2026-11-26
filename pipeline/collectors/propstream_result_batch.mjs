/** Parse only a completed, visibly captured provider batch. Does not submit tracing. */
const norm = value => String(value??'').toUpperCase().replace(/[^A-Z0-9]/g,'');
export function matchCompletedResults(queue, receipt) {
  if (receipt.status !== 'complete' || !/^A\d+$/.test(receipt.job) || !Array.isArray(receipt.rows)
      || receipt.rows.length !== queue.properties.length) throw Error('Complete matching batch required');
  const seen=new Set();
  return receipt.rows.map(row=>{
    if (!row.url.startsWith(`https://app.propstream.com/contact/${receipt.job}/`) || !/\/\d+$/.test(row.url)
        || !Array.isArray(row.cells) || ![8,9].includes(row.cells.length) || row.cells.some(c=>typeof c!=='string')) throw Error('Invalid provider row');
    const c=row.cells;
    const matches=queue.properties.filter(p=>norm(`${p.identity.property_address} ${p.identity.city} ${p.identity.state} ${p.identity.zip}`)===norm(c[5]));
    if (matches.length!==1) throw Error('Unique exact property match required');
    const property=matches[0];
    if (seen.has(property.identity.parcel_id)) throw Error('Duplicate property');
    seen.add(property.identity.parcel_id);
    const providerFlag=/\s*\(Litigator\)\s*$/.test(c[0]);
    if(norm(c[0].replace(/\s*\(Litigator\)\s*$/,''))!==norm(property.owner_name)) throw Error('Owner mismatch');
    const contacts=[];
    for(const [index,type] of [[1,'mobile'],[2,'landline'],[3,'unknown']]) {
      const pattern=/\(([2-9]\d{2})\)[ -]*(\d{3})-(\d{4})(\s*DNC)?/g;
      for(const m of c[index].matchAll(pattern)) contacts.push({name:property.owner_name,phone:`+1${m[1]}${m[2]}${m[3]}`,phone_type:type,dnc_status:m[4]?'listed':'unknown'});
      if(c[index].replace(pattern,'').trim()) throw Error('Unparsed phone evidence');
    }
    for(const email of c[4].trim().split(/[,\s]+/).filter(Boolean)) {
      if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw Error('Invalid email');
      contacts.push({name:property.owner_name,email,dnc_status:'unknown'});
    }
    if(contacts.length>20) throw Error('Oversized contact receipt');
    return {parcel_id:property.identity.parcel_id,identity:property.identity,owner_name:property.owner_name,
      provider_row_url:row.url,provider_litigator_flag:providerFlag,contacts,outreach_authorized:false};
  });
}
