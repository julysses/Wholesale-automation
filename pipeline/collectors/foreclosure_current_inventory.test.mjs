import test from 'node:test';
import assert from 'node:assert/strict';
import { addressKey, matchInventory } from './foreclosure_current_inventory.mjs';
const queue={properties:[{identity:{property_address:'12 EXAMPLE CT',city:'ANNA',zip:'75409',parcel_id:'R-1'},notices:[{document_id:'1',auction_date:'2026-11-03'}]}]};
const listing={url:'https://www.auction.com/details/example-1',address:'12 Example Court, Anna, TX 75409',text:'Starts in 20 days\nForeclosure Sale'};
const inventory={url:'https://www.auction.com/residential/tx/Collin-county',captured_at:'2026-10-14T18:00:00Z',rows:[listing]};
test('bulk inventory matches full identity and date without granting eligibility',()=>{
 const [row]=matchInventory(queue,inventory,'2026-10-14');
 assert.equal(row.stage,'current_listing_matched'); assert.equal(row.advertised_sale_date,'2026-11-03'); assert.equal(row.trace_eligible,false);
 assert.notEqual(addressKey('12 Example Ct Unit B, Anna, TX 75409'),addressKey(listing.address));
 assert.notEqual(addressKey('12 N Example Ct, Anna, TX 75409'),addressKey(listing.address));
});
test('stale, ambiguous, wrong-date, bank-owned and unmatched inventory stay held',()=>{
 const check=rows=>matchInventory(queue,{...inventory,rows},'2026-10-14')[0].stage;
 assert.equal(check([]),'current_listing_not_found');
 assert.equal(check([listing,{...listing,url:listing.url+'2'}]),'ambiguous_listing');
 assert.equal(check([{...listing,text:'Starts in 48 days Foreclosure Sale'}]),'sale_date_unresolved');
 assert.equal(check([{...listing,text:'Starts in 20 days Bank Owned'}]),'non_foreclosure_listing');
 assert.throws(()=>matchInventory(queue,inventory,'2026-10-15'),/stale/);
 assert.throws(()=>check([listing,listing]),/duplicate/);
});
