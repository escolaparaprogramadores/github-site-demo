const { JSDOM } = require('jsdom');
const { expect } = require('chai');
const fs = require('fs');

describe('Failing HTML Test', function() {
    it('should have an h1 tag with text "Nonexistent Heading"', function(done) {
        fs.readFile('index.html', 'utf8', (err, data) => {
            if (err) {
                throw err;
            }
            const dom = new JSDOM(data);
            const h1Element = dom.window.document.querySelector('h1');
            expect(h1Element).to.not.be.null;
            expect(h1Element.textContent).to.equal('Nonexistent Heading'); // This will fail
            done();
        });
    });
});
