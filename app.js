const posts = [
  {
    image:
      "https://placehold.co/100x100",

    caption:
      "Example Facebook Post",

    time:
      "2026-05-13 10:00 PM"
  }
];

const table =
  document.getElementById("postTable");

posts.forEach(post => {

  table.innerHTML += `
    <tr class="border-b">

      <td class="p-4">
        <img
          src="${post.image}"
          class="w-20 h-20 rounded-xl object-cover"
        />
      </td>

      <td class="p-4">
        ${post.caption}
      </td>

      <td class="p-4">
        ${post.time}
      </td>

    </tr>
  `;
});
