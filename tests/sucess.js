const { JSDOM } = require('jsdom');
const { expect } = require('chai');
const fs = require('fs');

describe('HTML Tests', function() {
    it('should have a title with class "title-k8s" and text "GitHub Actions"', function(done) {
        fs.readFile('index.html', 'utf8', (err, data) => {
            if (err) {
                throw err;
            }
            const dom = new JSDOM(data);
            const titleElement = dom.window.document.querySelector('title.title-k8s');
            expect(titleElement).to.not.be.null;
            expect(titleElement.textContent).to.equal('GitHub Actions');
            done();
        });
    });

    it('should have a meta charset tag with UTF-8', function(done) {
        fs.readFile('index.html', 'utf8', (err, data) => {
            if (err) {
                throw err;
            }
            const dom = new JSDOM(data);
            const metaCharset = dom.window.document.querySelector('meta[charset="UTF-8"]');
            expect(metaCharset).to.not.be.null;
            done();
        });
    });

    it('should have a link to the stylesheet "style.css"', function(done) {
        fs.readFile('index.html', 'utf8', (err, data) => {
            if (err) {
                throw err;
            }
            const dom = new JSDOM(data);
            const linkStylesheet = dom.window.document.querySelector('link[href="assets/css/style.css"]');
            expect(linkStylesheet).to.not.be.null;
            done();
        });
    });

    it('should have a div with class "body-wrap boxed-container"', function(done) {
        fs.readFile('index.html', 'utf8', (err, data) => {
            if (err) {
                throw err;
            }
            const dom = new JSDOM(data);
            const divContainer = dom.window.document.querySelector('div.body-wrap.boxed-container');
            expect(divContainer).to.not.be.null;
            done();
        });
    });
});
